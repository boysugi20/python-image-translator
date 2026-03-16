import os
import json
import logging
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter

from PIL import Image, ImageDraw, ImageFont
from deep_translator import GoogleTranslator
import easyocr


# ==================== 配置管理 ====================
@dataclass
class Config:
    """配置类"""
    # OCR配置
    ocr_languages: List[str]
    model_storage_directory: str
    ocr_width_threshold: float
    ocr_confidence_threshold: float
    ocr_decoder: str

    # 翻译配置
    source_language: str
    target_language: str

    # 目录配置
    input_folder: str
    output_folder: str

    # 图像处理配置
    background_margin: int
    color_discoloration_strength: int
    max_font_size: int
    font_path: str  # 字体文件路径

    # 性能配置
    max_workers: int

    @classmethod
    def from_file(cls, config_path: str = "config.json") -> 'Config':
        """从配置文件加载配置"""
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            return cls(**config_data)
        else:
            # 默认配置
            return cls.get_default()

    @classmethod
    def get_default(cls) -> 'Config':
        """获取默认配置"""
        return cls(
            ocr_languages=["ch_sim", "en"],
            model_storage_directory="model",
            ocr_width_threshold=0.8,
            ocr_confidence_threshold=0.4,
            ocr_decoder="wordbeamsearch",
            source_language="zh-CN",
            target_language="en",
            input_folder="input",
            output_folder="output",
            background_margin=10,
            color_discoloration_strength=40,
            max_font_size=500,
            font_path="C:/Windows/Fonts/msyh.ttc",  # 微软雅黑字体
            max_workers=4
        )

    def save(self, config_path: str = "config.json"):
        """保存配置到文件"""
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(self.__dict__, f, indent=4, ensure_ascii=False)


# ==================== 日志配置 ====================
def setup_logging(log_file: str = "translator.log"):
    """配置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )


# ==================== OCR处理器 ====================
class OCRProcessor:
    """OCR文字识别处理器"""

    def __init__(self, config: Config):
        self.config = config
        self.reader = None

    def initialize(self):
        """初始化OCR读取器"""
        try:
            logging.info(f"初始化OCR读取器，支持语言: {self.config.ocr_languages}")
            self.reader = easyocr.Reader(
                self.config.ocr_languages,
                model_storage_directory=self.config.model_storage_directory,
                gpu=False,
                download_enabled=True,
                verbose=True
            )
            logging.info("OCR读取器初始化成功")
        except Exception as e:
            logging.error(f"OCR初始化失败: {e}")
            raise

    def extract_text_boxes(self, image_path: str) -> List[Tuple[List, str]]:
        """
        从图像中提取文字和位置

        Args:
            image_path: 图像路径

        Returns:
            [(坐标框, 文字), ...]
        """
        if self.reader is None:
            raise RuntimeError("OCR读取器未初始化，请先调用initialize()")

        try:
            result = self.reader.readtext(
                image_path,
                width_ths=self.config.ocr_width_threshold,
                decoder=self.config.ocr_decoder
            )

            # 过滤低置信度结果
            text_boxes = [
                (entry[0], entry[1])
                for entry in result
                if entry[2] > self.config.ocr_confidence_threshold
            ]

            logging.info(f"识别到 {len(text_boxes)} 个文本框")
            return text_boxes

        except Exception as e:
            logging.error(f"OCR识别失败: {e}")
            return []


# ==================== 翻译器 ====================
class Translator:
    """文本翻译器"""

    def __init__(self, config: Config):
        self.config = config
        self.translator = GoogleTranslator(
            source=config.source_language,
            target=config.target_language
        )

    def translate(self, text: str) -> Optional[str]:
        """
        翻译文本

        Args:
            text: 待翻译文本

        Returns:
            翻译后的文本，失败返回None
        """
        if not text or not text.strip():
            return None

        try:
            translated = self.translator.translate(text)
            logging.debug(f"翻译: '{text}' -> '{translated}'")
            return translated
        except Exception as e:
            logging.error(f"翻译失败: {text}, 错误: {e}")
            return None

    def translate_batch(self, texts: List[str]) -> List[Optional[str]]:
        """批量翻译文本"""
        return [self.translate(text) for text in texts]


# ==================== 图像处理器 ====================
class ImageProcessor:
    """图像处理器"""

    def __init__(self, config: Config):
        self.config = config

    def calculate_font_size(
        self,
        image: Image.Image,
        text: str,
        width: int,
        height: int
    ) -> Tuple[Optional[ImageFont.FreeTypeFont], int, int]:
        """
        计算合适的字体大小

        Returns:
            (字体对象, x坐标, y坐标)
        """
        draw = ImageDraw.Draw(image)
        font = None
        x, y = 0, 0

        # 尝试加载指定的字体文件
        font_path = self.config.font_path
        if not os.path.exists(font_path):
            # 如果指定字体不存在，尝试常见的中文字体
            fallback_fonts = [
                "C:/Windows/Fonts/msyh.ttc",      # 微软雅黑
                "C:/Windows/Fonts/simhei.ttf",    # 黑体
                "C:/Windows/Fonts/simsun.ttc",    # 宋体
                "C:/Windows/Fonts/arial.ttf",     # Arial
            ]
            for fb_font in fallback_fonts:
                if os.path.exists(fb_font):
                    font_path = fb_font
                    logging.info(f"使用备用字体: {font_path}")
                    break

        for size in range(1, self.config.max_font_size):
            try:
                new_font = ImageFont.truetype(font_path, size=size)
            except Exception:
                # 如果字体加载失败，使用默认字体
                new_font = ImageFont.load_default(size=size)

            new_box = draw.textbbox((0, 0), text, font=new_font)

            new_w = new_box[2] - new_box[0]
            new_h = new_box[3] - new_box[1]

            if new_w > width or new_h > height:
                break

            font = new_font
            w, h = new_w, new_h
            box = new_box
            x = (width - w) // 2 - box[0]
            y = (height - h) // 2 - box[1]

        return font, x, y

    def adjust_color(self, color: Tuple[int, int, int], strength: int) -> Tuple[int, int, int]:
        """调整颜色亮度"""
        r, g, b = color[:3]
        r = max(0, min(255, r + strength))
        g = max(0, min(255, g + strength))
        b = max(0, min(255, b + strength))

        # 避免纯白色
        if r == 255 and g == 255 and b == 255:
            r, g, b = 245, 245, 245

        return (r, g, b)

    def get_background_color(
        self,
        image: Image.Image,
        x_min: int,
        y_min: int,
        x_max: int,
        y_max: int
    ) -> Tuple[int, int, int]:
        """获取背景颜色"""
        image = image.convert('RGBA')
        margin = self.config.background_margin

        edge_region = image.crop((
            max(x_min - margin, 0),
            max(y_min - margin, 0),
            min(x_max + margin, image.width),
            min(y_max + margin, image.height),
        ))

        pixels = list(edge_region.getdata())
        opaque_pixels = [pixel[:3] for pixel in pixels if pixel[3] > 0]

        if not opaque_pixels:
            background_color = (255, 255, 255)
        else:
            most_common = Counter(opaque_pixels).most_common(1)[0][0]
            background_color = most_common

        background_color = self.adjust_color(
            background_color,
            self.config.color_discoloration_strength
        )
        return background_color

    def get_text_color(self, background_color: Tuple[int, int, int]) -> str:
        """根据背景颜色计算文字颜色"""
        luminance = (
            0.299 * background_color[0] +
            0.587 * background_color[1] +
            0.114 * background_color[2]
        ) / 255

        return "black" if luminance > 0.5 else "white"

    def get_bounding_box(self, coordinates: List[List[int]]) -> Tuple[int, int, int, int]:
        """计算文本框的边界"""
        x_min = min(coord[0] for coord in coordinates)
        y_min = min(coord[1] for coord in coordinates)
        x_max = max(coord[0] for coord in coordinates)
        y_max = max(coord[1] for coord in coordinates)
        return x_min, y_min, x_max, y_max

    def replace_text(
        self,
        image_path: str,
        text_boxes: List[Tuple[List, str]],
        translations: List[Optional[str]]
    ) -> Image.Image:
        """
        在图像上替换文本

        Args:
            image_path: 图像路径
            text_boxes: OCR识别的文本框
            translations: 翻译后的文本

        Returns:
            处理后的图像
        """
        image = Image.open(image_path)
        draw = ImageDraw.Draw(image)

        for (coordinates, original_text), translated_text in zip(text_boxes, translations):
            if translated_text is None:
                continue

            # 获取边界框
            x_min, y_min, x_max, y_max = self.get_bounding_box(coordinates)

            # 获取背景颜色
            bg_color = self.get_background_color(image, x_min, y_min, x_max, y_max)

            # 覆盖原文本
            draw.rectangle(((x_min, y_min), (x_max, y_max)), fill=bg_color)

            # 计算字体和位置
            width, height = x_max - x_min, y_max - y_min
            font, x_offset, y_offset = self.calculate_font_size(
                image, translated_text, width, height
            )

            # 绘制翻译文本
            if font:
                text_color = self.get_text_color(bg_color)
                draw.text(
                    (x_min + x_offset, y_min + y_offset),
                    translated_text,
                    fill=text_color,
                    font=font
                )

        return image


# ==================== 主处理器 ====================
class ImageTranslator:
    """图像翻译主处理器"""

    def __init__(self, config: Config):
        self.config = config
        self.ocr = OCRProcessor(config)
        self.translator = Translator(config)
        self.image_processor = ImageProcessor(config)

    def initialize(self):
        """初始化所有组件"""
        self.ocr.initialize()

        # 确保输出目录存在
        os.makedirs(self.config.output_folder, exist_ok=True)

    def process_single_image(self, image_path: str, output_path: str) -> bool:
        """
        处理单张图片

        Args:
            image_path: 输入图片路径
            output_path: 输出图片路径

        Returns:
            是否处理成功
        """
        try:
            logging.info(f"开始处理: {image_path}")

            # OCR识别
            text_boxes = self.ocr.extract_text_boxes(image_path)

            if not text_boxes:
                logging.warning(f"未识别到文本: {image_path}")
                return False

            # 翻译
            texts = [text for _, text in text_boxes]
            translations = self.translator.translate_batch(texts)

            # 替换文本
            result_image = self.image_processor.replace_text(
                image_path, text_boxes, translations
            )

            # 保存
            result_image.save(output_path)
            logging.info(f"处理完成，保存至: {output_path}")

            return True

        except Exception as e:
            logging.error(f"处理失败 {image_path}: {e}", exc_info=True)
            return False

    def process_folder(self, use_parallel: bool = True) -> Dict[str, int]:
        """
        批量处理文件夹中的图片

        Args:
            use_parallel: 是否使用并行处理

        Returns:
            处理统计信息
        """
        input_path = Path(self.config.input_folder)
        output_path = Path(self.config.output_folder)

        # 获取所有图片文件
        image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}
        image_files = [
            f for f in input_path.iterdir()
            if f.is_file() and f.suffix.lower() in image_extensions
        ]

        if not image_files:
            logging.warning(f"未找到图片文件: {input_path}")
            return {"total": 0, "success": 0, "failed": 0}

        logging.info(f"找到 {len(image_files)} 个图片文件")

        stats = {"total": len(image_files), "success": 0, "failed": 0}

        if use_parallel and len(image_files) > 1:
            # 并行处理
            with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
                futures = {}

                for img_file in image_files:
                    output_file = output_path / f"{img_file.stem}-translated{img_file.suffix}"
                    future = executor.submit(
                        self.process_single_image,
                        str(img_file),
                        str(output_file)
                    )
                    futures[future] = img_file.name

                for future in as_completed(futures):
                    filename = futures[future]
                    try:
                        success = future.result()
                        if success:
                            stats["success"] += 1
                        else:
                            stats["failed"] += 1
                    except Exception as e:
                        logging.error(f"处理失败 {filename}: {e}")
                        stats["failed"] += 1
        else:
            # 串行处理
            for img_file in image_files:
                output_file = output_path / f"{img_file.stem}-translated{img_file.suffix}"
                success = self.process_single_image(str(img_file), str(output_file))

                if success:
                    stats["success"] += 1
                else:
                    stats["failed"] += 1

        return stats


# ==================== 主函数 ====================
def main():
    """主函数"""
    # 设置日志
    setup_logging()

    # 加载配置
    config = Config.get_default()

    # 如果配置文件不存在，创建默认配置
    if not os.path.exists("config.json"):
        logging.info("创建默认配置文件: config.json")
        config.save()
    else:
        config = Config.from_file()

    # 创建翻译器
    translator = ImageTranslator(config)

    try:
        # 初始化
        translator.initialize()

        # 处理图片
        stats = translator.process_folder(use_parallel=True)

        # 输出统计
        logging.info(f"\n{'='*50}")
        logging.info(f"处理完成!")
        logging.info(f"总计: {stats['total']} 张")
        logging.info(f"成功: {stats['success']} 张")
        logging.info(f"失败: {stats['failed']} 张")
        logging.info(f"{'='*50}")

    except KeyboardInterrupt:
        logging.info("用户中断处理")
    except Exception as e:
        logging.error(f"程序异常: {e}", exc_info=True)


if __name__ == "__main__":
    main()
