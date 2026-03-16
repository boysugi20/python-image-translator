import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path
import threading
from PIL import Image, ImageTk, ImageDraw, ImageFont
import logging
from typing import List, Tuple, Optional

from image_translator_optimized import (
    Config, ImageTranslator, OCRProcessor, Translator, ImageProcessor
)


class TextBoxItem:
    """文本框项"""
    def __init__(self, index, coordinates, text, selected=True):
        self.index = index
        self.coordinates = coordinates
        self.text = text
        self.selected = selected
        self.translated_text = None
        # 样式设置
        self.font_size = None  # None表示自动计算
        self.font_path = None  # None表示使用默认字体
        self.text_color = None  # None表示自动计算（黑/白）


class ImageTranslatorGUI:
    """图像翻译器图形界面"""

    def __init__(self, root):
        self.root = root
        self.root.title("图像翻译器 - 交互式选择")
        self.root.geometry("1400x800")

        # 配置
        self.config = Config.from_file() if os.path.exists("config.json") else Config.get_default()
        self.translator = None
        self.processing = False

        # 当前图片相关
        self.current_image_path = None
        self.current_image = None
        self.display_image = None
        self.photo_image = None
        self.text_boxes = []  # List[TextBoxItem]
        self.scale_factor = 1.0
        self.current_edit_index = None  # 当前正在编辑的文本框索引

        # 手动框选相关
        self.manual_select_mode = False  # 是否处于手动框选模式
        self.select_start_x = None
        self.select_start_y = None
        self.select_rect_id = None  # 当前绘制的矩形框ID

        # 设置样式
        self.setup_styles()

        # 创建界面
        self.create_widgets()

        # 设置日志处理器
        self.setup_gui_logging()

    def setup_styles(self):
        """设置界面样式"""
        style = ttk.Style()
        style.theme_use('clam')

        # 配置按钮样式
        style.configure('Primary.TButton', padding=10, font=('Microsoft YaHei', 10))
        style.configure('Success.TButton', padding=8, font=('Microsoft YaHei', 9))
        style.configure('TLabel', font=('Microsoft YaHei', 9))
        style.configure('Title.TLabel', font=('Microsoft YaHei', 12, 'bold'))

    def create_widgets(self):
        """创建所有界面组件"""
        # 主容器 - 使用PanedWindow分割左右
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 左侧面板 - 图片预览
        left_frame = ttk.Frame(main_paned)
        main_paned.add(left_frame, weight=2)

        # 右侧面板 - 控制和文本框列表
        right_frame = ttk.Frame(main_paned)
        main_paned.add(right_frame, weight=1)

        # 创建左侧内容
        self.create_left_panel(left_frame)

        # 创建右侧内容
        self.create_right_panel(right_frame)

    def create_left_panel(self, parent):
        """创建左侧图片预览面板"""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        # 顶部工具栏
        toolbar = ttk.Frame(parent, padding="5")
        toolbar.grid(row=0, column=0, sticky=(tk.W, tk.E))

        ttk.Button(toolbar, text="选择图片", command=self.select_image).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="识别文本", command=self.detect_text).pack(side=tk.LEFT, padx=5)

        # 手动框选模式切换按钮
        self.manual_mode_var = tk.BooleanVar(value=False)
        manual_check = ttk.Checkbutton(
            toolbar,
            text="手动框选模式",
            variable=self.manual_mode_var,
            command=self.toggle_manual_mode
        )
        manual_check.pack(side=tk.LEFT, padx=5)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=5, fill=tk.Y)

        ttk.Button(toolbar, text="全选", command=self.select_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="全不选", command=self.deselect_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="反选", command=self.invert_selection).pack(side=tk.LEFT, padx=5)

        # 图片显示区域
        image_frame = ttk.LabelFrame(parent, text="图片预览（点击文本框切换选择状态）", padding="10")
        image_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        image_frame.columnconfigure(0, weight=1)
        image_frame.rowconfigure(0, weight=1)

        # 创建Canvas用于显示图片
        self.canvas = tk.Canvas(image_frame, bg='gray', cursor='cross')
        self.canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 添加滚动条
        h_scrollbar = ttk.Scrollbar(image_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        h_scrollbar.grid(row=1, column=0, sticky=(tk.W, tk.E))
        v_scrollbar = ttk.Scrollbar(image_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        v_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))

        self.canvas.configure(xscrollcommand=h_scrollbar.set, yscrollcommand=v_scrollbar.set)

        # 绑定鼠标事件
        self.canvas.bind('<Button-1>', self.on_canvas_mouse_down)
        self.canvas.bind('<B1-Motion>', self.on_canvas_mouse_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_canvas_mouse_up)

    def create_right_panel(self, parent):
        """创建右侧控制面板"""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        parent.rowconfigure(2, weight=1)

        # 1. 翻译设置和高级设置（合并为一行）
        self.create_settings_section(parent)

        # 2. 文本框列表
        self.create_textbox_list(parent)

        # 3. 日志输出
        self.create_log_section(parent)

        # 4. 控制按钮
        self.create_control_section(parent)

    def create_settings_section(self, parent):
        """创建设置区域（翻译+高级设置合并）"""
        frame = ttk.LabelFrame(parent, text="设置", padding="10")
        frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=5)

        # 语言字典
        languages = {
            "英文": "en",
            "简体中文": "zh-CN",
            "繁体中文": "zh-TW",
            "日文": "ja",
            "韩文": "ko",
            "法文": "fr",
            "德文": "de",
            "西班牙文": "es",
            "俄文": "ru"
        }
        self.languages_dict = languages

        # 第一行：语言设置
        row1 = ttk.Frame(frame)
        row1.pack(fill=tk.X, pady=2)

        ttk.Label(row1, text="源语言:", width=8).pack(side=tk.LEFT, padx=5)
        self.source_lang_var = tk.StringVar(value=self.get_language_name(self.config.source_language, languages))
        source_combo = ttk.Combobox(row1, textvariable=self.source_lang_var, values=list(languages.keys()), state='readonly', width=10)
        source_combo.pack(side=tk.LEFT, padx=5)

        ttk.Label(row1, text="→", font=('Arial', 14)).pack(side=tk.LEFT, padx=2)
        ttk.Button(row1, text="⇄", command=self.swap_languages, width=3).pack(side=tk.LEFT, padx=2)

        ttk.Label(row1, text="目标语言:", width=8).pack(side=tk.LEFT, padx=(10, 5))
        self.target_lang_var = tk.StringVar(value=self.get_language_name(self.config.target_language, languages))
        target_combo = ttk.Combobox(row1, textvariable=self.target_lang_var, values=list(languages.keys()), state='readonly', width=10)
        target_combo.pack(side=tk.LEFT, padx=5)

        # 第二行：高级设置
        row2 = ttk.Frame(frame)
        row2.pack(fill=tk.X, pady=2)

        ttk.Label(row2, text="OCR置信度:", width=10).pack(side=tk.LEFT, padx=5)
        self.confidence_var = tk.DoubleVar(value=self.config.ocr_confidence_threshold)
        confidence_scale = ttk.Scale(row2, from_=0.0, to=1.0, variable=self.confidence_var, orient=tk.HORIZONTAL, length=100)
        confidence_scale.pack(side=tk.LEFT, padx=5)
        self.confidence_label = ttk.Label(row2, text=f"{self.confidence_var.get():.2f}", width=4)
        self.confidence_label.pack(side=tk.LEFT, padx=2)
        self.confidence_var.trace_add('write', lambda *args: self.confidence_label.config(text=f"{self.confidence_var.get():.2f}"))

        ttk.Label(row2, text="最大字体:", width=8).pack(side=tk.LEFT, padx=(10, 5))
        self.font_size_var = tk.IntVar(value=self.config.max_font_size)
        ttk.Spinbox(row2, from_=10, to=1000, textvariable=self.font_size_var, width=8).pack(side=tk.LEFT, padx=5)

    def create_translation_section(self, parent):
        """创建翻译设置区域"""
        frame = ttk.LabelFrame(parent, text="翻译设置", padding="10")
        frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=5)

        # 语言选择
        languages = {
            "英文": "en",
            "简体中文": "zh-CN",
            "繁体中文": "zh-TW",
            "日文": "ja",
            "韩文": "ko",
            "法文": "fr",
            "德文": "de",
            "西班牙文": "es",
            "俄文": "ru"
        }

        # 源语言
        ttk.Label(frame, text="源语言:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.source_lang_var = tk.StringVar(value=self.get_language_name(self.config.source_language, languages))
        source_combo = ttk.Combobox(frame, textvariable=self.source_lang_var, values=list(languages.keys()), state='readonly', width=12)
        source_combo.grid(row=0, column=1, sticky=tk.W, padx=5)

        # 箭头和切换按钮
        ttk.Label(frame, text="→", font=('Arial', 16)).grid(row=0, column=2, padx=5)
        ttk.Button(frame, text="⇄", command=self.swap_languages, width=3).grid(row=0, column=3, padx=2)

        # 目标语言
        ttk.Label(frame, text="目标语言:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.target_lang_var = tk.StringVar(value=self.get_language_name(self.config.target_language, languages))
        target_combo = ttk.Combobox(frame, textvariable=self.target_lang_var, values=list(languages.keys()), state='readonly', width=12)
        target_combo.grid(row=1, column=1, sticky=tk.W, padx=5)

        self.languages_dict = languages

    def create_advanced_section(self, parent):
        """创建高级设置区域"""
        frame = ttk.LabelFrame(parent, text="高级设置", padding="10")
        frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=5)

        # OCR 置信度阈值
        ttk.Label(frame, text="OCR置信度:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.confidence_var = tk.DoubleVar(value=self.config.ocr_confidence_threshold)
        confidence_scale = ttk.Scale(frame, from_=0.0, to=1.0, variable=self.confidence_var, orient=tk.HORIZONTAL, length=150)
        confidence_scale.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5)
        self.confidence_label = ttk.Label(frame, text=f"{self.confidence_var.get():.2f}")
        self.confidence_label.grid(row=0, column=2, padx=5)
        self.confidence_var.trace_add('write', lambda *args: self.confidence_label.config(text=f"{self.confidence_var.get():.2f}"))

        # 最大字体大小
        ttk.Label(frame, text="最大字体:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.font_size_var = tk.IntVar(value=self.config.max_font_size)
        ttk.Spinbox(frame, from_=10, to=1000, textvariable=self.font_size_var, width=8).grid(row=1, column=1, sticky=tk.W, padx=5)

        frame.columnconfigure(1, weight=1)

    def create_textbox_list(self, parent):
        """创建文本框列表"""
        frame = ttk.LabelFrame(parent, text="识别到的文本框", padding="10")
        frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        # 创建Treeview
        columns = ('#', '☑', '原文', '译文')
        self.tree = ttk.Treeview(frame, columns=columns, show='headings', height=10)
        self.tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 设置列
        self.tree.heading('#', text='#')
        self.tree.heading('☑', text='☑')
        self.tree.heading('原文', text='原文')
        self.tree.heading('译文', text='译文')

        self.tree.column('#', width=35, anchor='center')
        self.tree.column('☑', width=35, anchor='center')
        self.tree.column('原文', width=180)
        self.tree.column('译文', width=180)

        # 滚动条
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.tree.configure(yscrollcommand=scrollbar.set)

        # 单击切换选择状态
        self.tree.bind('<Button-1>', self.on_tree_click)

        # 编辑框区域
        edit_frame = ttk.LabelFrame(frame, text="编辑选中的文本框", padding="10")
        edit_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        # 第一行：译文编辑
        row1 = ttk.Frame(edit_frame)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="译文:", width=10).pack(side=tk.LEFT, padx=5)
        self.edit_var = tk.StringVar()
        self.edit_entry = ttk.Entry(row1, textvariable=self.edit_var)
        self.edit_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Label(row1, text="(按回车保存)", font=('Microsoft YaHei', 8)).pack(side=tk.LEFT)

        # 绑定回车键自动保存
        self.edit_entry.bind('<Return>', lambda e: self.apply_edit())
        # 绑定失去焦点自动保存
        self.edit_entry.bind('<FocusOut>', lambda e: self.apply_edit_auto())

        # 第二行：字体大小
        row2 = ttk.Frame(edit_frame)
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="字体大小:", width=10).pack(side=tk.LEFT, padx=5)
        self.font_size_edit_var = tk.StringVar(value="自动")
        self.font_size_combo = ttk.Combobox(
            row2,
            textvariable=self.font_size_edit_var,
            values=['自动', '10', '12', '14', '16', '18', '20', '24', '28', '32', '36', '40', '48', '56', '64', '72', '80', '96', '128', '150', '200', '250', '300'],
            width=10,
            state='readonly'
        )
        self.font_size_combo.pack(side=tk.LEFT, padx=5)
        self.font_size_combo.bind('<<ComboboxSelected>>', self.on_style_changed)

        # 字体选择
        ttk.Label(row2, text="字体:", width=8).pack(side=tk.LEFT, padx=(20, 5))
        self.font_edit_var = tk.StringVar(value="默认")
        self.font_combo = ttk.Combobox(
            row2,
            textvariable=self.font_edit_var,
            values=['默认', '微软雅黑', '黑体', '宋体', '楷体', 'Arial', 'Times New Roman'],
            width=15,
            state='readonly'
        )
        self.font_combo.pack(side=tk.LEFT, padx=5)
        self.font_combo.bind('<<ComboboxSelected>>', self.on_style_changed)

        # 第三行：文字颜色
        row3 = ttk.Frame(edit_frame)
        row3.pack(fill=tk.X, pady=2)
        ttk.Label(row3, text="文字颜色:", width=10).pack(side=tk.LEFT, padx=5)
        self.color_edit_var = tk.StringVar(value="自动")
        self.color_combo = ttk.Combobox(
            row3,
            textvariable=self.color_edit_var,
            values=['自动', '黑色', '白色', '红色', '绿色', '蓝色', '黄色', '橙色', '紫色'],
            width=10,
            state='readonly'
        )
        self.color_combo.pack(side=tk.LEFT, padx=5)
        self.color_combo.bind('<<ComboboxSelected>>', self.on_style_changed)

        # 自定义颜色按钮
        ttk.Button(row3, text="自定义颜色...", command=self.choose_custom_color).pack(side=tk.LEFT, padx=5)

        # 重置按钮
        ttk.Button(row3, text="重置样式", command=self.reset_style).pack(side=tk.LEFT, padx=(20, 5))

    def create_log_section(self, parent):
        """创建日志输出区域"""
        frame = ttk.LabelFrame(parent, text="运行日志", padding="10")
        frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        # 日志文本框
        self.log_text = scrolledtext.ScrolledText(
            frame,
            height=8,
            wrap=tk.WORD,
            font=('Consolas', 8)
        )
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

    def create_control_section(self, parent):
        """创建控制按钮区域"""
        frame = ttk.Frame(parent, padding="10")
        frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=5)

        # 翻译选中文本按钮
        self.translate_button = ttk.Button(
            frame,
            text="翻译选中的文本",
            command=self.translate_selected,
            style='Primary.TButton'
        )
        self.translate_button.pack(fill=tk.X, pady=2)

        # 应用翻译按钮
        self.apply_button = ttk.Button(
            frame,
            text="应用翻译并保存",
            command=self.apply_translation,
            style='Success.TButton',
            state=tk.DISABLED
        )
        self.apply_button.pack(fill=tk.X, pady=2)

        # 保存配置
        ttk.Button(frame, text="保存配置", command=self.save_config).pack(fill=tk.X, pady=2)

    def setup_gui_logging(self):
        """设置GUI日志处理器"""
        class GUILogHandler(logging.Handler):
            def __init__(self, text_widget):
                super().__init__()
                self.text_widget = text_widget

            def emit(self, record):
                msg = self.format(record)
                def append():
                    self.text_widget.insert(tk.END, msg + '\n')
                    self.text_widget.see(tk.END)
                self.text_widget.after(0, append)

        # 配置日志
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        logger.handlers.clear()

        # 添加GUI处理器
        gui_handler = GUILogHandler(self.log_text)
        gui_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(gui_handler)

        # 添加文件处理器
        file_handler = logging.FileHandler('translator_gui.log', encoding='utf-8')
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(file_handler)

    def get_language_name(self, code, languages):
        """根据语言代码获取语言名称"""
        for name, lang_code in languages.items():
            if lang_code == code:
                return name
        return "英文"

    def swap_languages(self):
        """交换源语言和目标语言"""
        source = self.source_lang_var.get()
        target = self.target_lang_var.get()
        self.source_lang_var.set(target)
        self.target_lang_var.set(source)

    def select_image(self):
        """选择图片"""
        filename = filedialog.askopenfilename(
            title="选择图片",
            filetypes=[
                ("图片文件", "*.jpg *.jpeg *.png *.webp *.bmp"),
                ("所有文件", "*.*")
            ]
        )
        if filename:
            self.load_image(filename)

    def load_image(self, image_path):
        """加载图片"""
        try:
            self.current_image_path = image_path
            self.current_image = Image.open(image_path)
            self.text_boxes = []

            # 显示图片
            self.display_image_on_canvas()

            logging.info(f"已加载图片: {image_path}")
        except Exception as e:
            messagebox.showerror("错误", f"加载图片失败: {e}")
            logging.error(f"加载图片失败: {e}")

    def display_image_on_canvas(self, draw_boxes=False):
        """在Canvas上显示图片"""
        if self.current_image is None:
            return

        # 复制图片用于显示
        display_img = self.current_image.copy()

        # 如果需要绘制文本框
        if draw_boxes and self.text_boxes:
            draw = ImageDraw.Draw(display_img, 'RGBA')

            for box_item in self.text_boxes:
                coords = box_item.coordinates
                color = 'lime' if box_item.selected else 'red'
                width = 3 if box_item.selected else 2

                # 绘制矩形
                points = [(int(p[0]), int(p[1])) for p in coords]
                draw.polygon(points, outline=color, width=width)

                # 绘制序号
                x_min = min(p[0] for p in coords)
                y_min = min(p[1] for p in coords)

                # 序号文字
                number_text = str(box_item.index + 1)

                try:
                    number_font = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", 28)
                except:
                    try:
                        number_font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 28)
                    except:
                        number_font = ImageFont.load_default()

                # 计算文字边界框
                bbox = draw.textbbox((0, 0), number_text, font=number_font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]

                # 序号位置
                number_x = x_min
                number_y = max(5, y_min - text_height - 8)

                # 绘制序号背景（半透明矩形）
                padding = 4
                bg_color = (0, 255, 0, 100) if box_item.selected else (255, 0, 0, 100)  # RGBA
                draw.rectangle(
                    [number_x - padding, number_y - padding,
                     number_x + text_width + padding, number_y + text_height + padding],
                    fill=bg_color
                )

                # 绘制白色序号文字
                draw.text((number_x, number_y), number_text, fill='white', font=number_font)

        # 调整图片大小以适应Canvas
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()

        if canvas_width <= 1 or canvas_height <= 1:
            canvas_width = 800
            canvas_height = 600

        img_width, img_height = display_img.size
        scale_x = canvas_width / img_width
        scale_y = canvas_height / img_height
        self.scale_factor = min(scale_x, scale_y, 1.0)

        new_width = int(img_width * self.scale_factor)
        new_height = int(img_height * self.scale_factor)

        display_img = display_img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # 转换为PhotoImage
        self.photo_image = ImageTk.PhotoImage(display_img)

        # 显示在Canvas上
        self.canvas.delete('all')
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo_image)
        self.canvas.config(scrollregion=(0, 0, new_width, new_height))

    def detect_text(self):
        """识别文本"""
        if self.current_image_path is None:
            messagebox.showwarning("警告", "请先选择图片")
            return

        def detect():
            try:
                logging.info("正在初始化OCR...")
                self.update_config_from_gui()

                ocr = OCRProcessor(self.config)
                ocr.initialize()

                logging.info("正在识别文本...")
                text_boxes = ocr.extract_text_boxes(self.current_image_path)

                if not text_boxes:
                    messagebox.showinfo("提示", "未识别到文本")
                    return

                # 创建TextBoxItem列表
                self.text_boxes = [
                    TextBoxItem(i, coords, text, selected=True)
                    for i, (coords, text) in enumerate(text_boxes)
                ]

                logging.info(f"识别到 {len(self.text_boxes)} 个文本框")

                # 更新显示
                self.root.after(0, self.update_display)

            except Exception as e:
                logging.error(f"文本识别失败: {e}", exc_info=True)
                messagebox.showerror("错误", f"文本识别失败: {e}")

        # 在后台线程运行
        thread = threading.Thread(target=detect)
        thread.daemon = True
        thread.start()

    def update_display(self):
        """更新显示（图片和列表）"""
        # 更新图片显示
        self.display_image_on_canvas(draw_boxes=True)

        # 更新文本框列表
        self.tree.delete(*self.tree.get_children())
        for i, box_item in enumerate(self.text_boxes):
            # 更新索引（防止删除后索引不连续）
            box_item.index = i

            # 序号
            number = str(box_item.index + 1)
            # 复选框符号
            checkbox = '☑' if box_item.selected else '☐'
            # 译文
            translated = box_item.translated_text if box_item.translated_text else ''

            self.tree.insert('', tk.END, values=(number, checkbox, box_item.text, translated), tags=(str(box_item.index),))

    def toggle_manual_mode(self):
        """切换手动框选模式"""
        self.manual_select_mode = self.manual_mode_var.get()
        if self.manual_select_mode:
            self.canvas.config(cursor='crosshair')
            logging.info("已进入手动框选模式 - 拖拽鼠标框选文字区域")
        else:
            self.canvas.config(cursor='arrow')
            logging.info("已退出手动框选模式")

    def on_canvas_mouse_down(self, event):
        """鼠标按下事件"""
        if self.manual_select_mode:
            # 手动框选模式：开始绘制矩形
            self.select_start_x = event.x
            self.select_start_y = event.y
        else:
            # 普通模式：处理点击
            self.on_canvas_click(event)

    def on_canvas_mouse_drag(self, event):
        """鼠标拖拽事件"""
        if not self.manual_select_mode or self.select_start_x is None:
            return

        # 删除之前的临时矩形
        if self.select_rect_id:
            self.canvas.delete(self.select_rect_id)

        # 绘制新的矩形
        self.select_rect_id = self.canvas.create_rectangle(
            self.select_start_x, self.select_start_y,
            event.x, event.y,
            outline='yellow',
            width=3,
            dash=(5, 5)
        )

    def on_canvas_mouse_up(self, event):
        """鼠标释放事件"""
        if not self.manual_select_mode or self.select_start_x is None:
            return

        # 删除临时矩形
        if self.select_rect_id:
            self.canvas.delete(self.select_rect_id)
            self.select_rect_id = None

        # 计算实际坐标（考虑缩放）
        x1 = min(self.select_start_x, event.x) / self.scale_factor
        y1 = min(self.select_start_y, event.y) / self.scale_factor
        x2 = max(self.select_start_x, event.x) / self.scale_factor
        y2 = max(self.select_start_y, event.y) / self.scale_factor

        # 检查框选区域是否太小
        if abs(x2 - x1) < 10 or abs(y2 - y1) < 10:
            logging.warning("框选区域太小，请重新框选")
            self.select_start_x = None
            self.select_start_y = None
            return

        # 重置起点
        self.select_start_x = None
        self.select_start_y = None

        # 对框选区域进行OCR识别
        self.recognize_manual_region(x1, y1, x2, y2)

    def recognize_manual_region(self, x1, y1, x2, y2):
        """对手动框选的区域进行OCR识别"""
        if not self.current_image_path:
            return

        def recognize():
            try:
                logging.info(f"正在识别框选区域: ({int(x1)}, {int(y1)}) - ({int(x2)}, {int(y2)})")

                # 裁剪图片区域
                image = Image.open(self.current_image_path)
                cropped = image.crop((int(x1), int(y1), int(x2), int(y2)))

                # 保存临时图片
                temp_path = "temp_crop.png"
                cropped.save(temp_path)

                # OCR识别
                self.update_config_from_gui()
                ocr = OCRProcessor(self.config)
                if not hasattr(ocr, 'reader') or ocr.reader is None:
                    ocr.initialize()

                # 识别裁剪区域
                result = ocr.reader.readtext(
                    temp_path,
                    width_ths=self.config.ocr_width_threshold,
                    decoder=self.config.ocr_decoder
                )

                # 删除临时文件
                if os.path.exists(temp_path):
                    os.remove(temp_path)

                if not result:
                    logging.warning("未在框选区域识别到文字")
                    messagebox.showinfo("提示", "未在框选区域识别到文字")
                    return

                # 提取文字
                texts = [entry[1] for entry in result if entry[2] > self.config.ocr_confidence_threshold]
                if not texts:
                    logging.warning("框选区域文字置信度过低")
                    messagebox.showinfo("提示", "识别到的文字置信度过低")
                    return

                combined_text = ' '.join(texts)
                logging.info(f"识别到文字: {combined_text}")

                # 创建文本框坐标（矩形四个角）
                coordinates = [
                    [x1, y1],
                    [x2, y1],
                    [x2, y2],
                    [x1, y2]
                ]

                # 添加到文本框列表
                new_index = len(self.text_boxes)
                new_box = TextBoxItem(new_index, coordinates, combined_text, selected=True)
                self.text_boxes.append(new_box)

                logging.info(f"已添加手动框选的文本框 #{new_index + 1}: {combined_text}")

                # 更新显示
                self.root.after(0, self.update_display)

                # 自动跳转到新添加的项
                self.root.after(100, lambda: self.jump_to_item_in_tree(new_index))
                self.root.after(100, lambda: self.show_in_editor(new_index))

            except Exception as e:
                logging.error(f"识别框选区域失败: {e}", exc_info=True)
                messagebox.showerror("错误", f"识别失败: {e}")

        # 在后台线程运行
        thread = threading.Thread(target=recognize)
        thread.daemon = True
        thread.start()

    def on_canvas_click(self, event):
        """Canvas点击事件 - 切换文本框选择状态（仅在非手动框选模式下）"""
        if not self.text_boxes:
            return

        # 获取点击位置（考虑缩放）
        x = event.x / self.scale_factor
        y = event.y / self.scale_factor

        # 检查点击是否在某个文本框内
        for box_item in self.text_boxes:
            coords = box_item.coordinates
            x_min = min(p[0] for p in coords)
            y_min = min(p[1] for p in coords)
            x_max = max(p[0] for p in coords)
            y_max = max(p[1] for p in coords)

            if x_min <= x <= x_max and y_min <= y <= y_max:
                # 切换选择状态
                box_item.selected = not box_item.selected
                logging.info(f"文本框 #{box_item.index + 1} {'选中' if box_item.selected else '取消选中'}: {box_item.text}")

                # 更新显示
                self.update_display()

                # 在右侧列表中定位到该项
                self.jump_to_item_in_tree(box_item.index)

                # 在编辑框中显示
                self.show_in_editor(box_item.index)

                break

    def jump_to_item_in_tree(self, index):
        """在Treeview中跳转到指定项"""
        # 获取所有项
        items = self.tree.get_children()

        if index < len(items):
            item_id = items[index]

            # 选中该项
            self.tree.selection_set(item_id)

            # 滚动到该项使其可见
            self.tree.see(item_id)

            # 设置焦点
            self.tree.focus(item_id)

    def on_tree_click(self, event):
        """Treeview点击事件"""
        # 获取点击的区域
        region = self.tree.identify_region(event.x, event.y)

        if region == "cell":
            # 获取点击的列
            column = self.tree.identify_column(event.x)
            item = self.tree.identify_row(event.y)

            if not item:
                return

            index = int(self.tree.item(item, 'tags')[0])

            # 如果点击的是第二列（复选框列），切换选择状态
            if column == '#2':  # 复选框列
                self.text_boxes[index].selected = not self.text_boxes[index].selected
                self.update_display()
                logging.info(f"文本框 #{index + 1} {'选中' if self.text_boxes[index].selected else '取消选中'}")
            else:
                # 其他列，选中该项并显示在编辑框中
                self.tree.selection_set(item)
                self.show_in_editor(index)

    def show_in_editor(self, index):
        """在编辑框中显示选中的文本"""
        # 先保存之前的编辑
        if hasattr(self, 'current_edit_index') and self.current_edit_index is not None:
            self.apply_edit_auto()

        box_item = self.text_boxes[index]

        # 显示译文
        if box_item.translated_text:
            self.edit_var.set(box_item.translated_text)
        else:
            self.edit_var.set(box_item.text)

        # 显示字体大小
        if box_item.font_size is None:
            self.font_size_edit_var.set("自动")
        else:
            self.font_size_edit_var.set(str(box_item.font_size))

        # 显示字体
        if box_item.font_path is None:
            self.font_edit_var.set("默认")
        else:
            # 根据路径推断字体名称
            font_name = self.get_font_name_from_path(box_item.font_path)
            self.font_edit_var.set(font_name)

        # 显示颜色
        if box_item.text_color is None:
            self.color_edit_var.set("自动")
        else:
            color_name = self.get_color_name(box_item.text_color)
            self.color_edit_var.set(color_name)

        # 保存当前编辑的索引
        self.current_edit_index = index

    def get_font_name_from_path(self, font_path):
        """根据字体路径获取字体名称"""
        font_map = {
            'msyh.ttc': '微软雅黑',
            'msyhbd.ttc': '微软雅黑',
            'simhei.ttf': '黑体',
            'simsun.ttc': '宋体',
            'simkai.ttf': '楷体',
            'arial.ttf': 'Arial',
            'times.ttf': 'Times New Roman'
        }
        for key, value in font_map.items():
            if key in font_path.lower():
                return value
        return "默认"

    def get_color_name(self, color):
        """根据颜色值获取颜色名称"""
        color_map = {
            'black': '黑色',
            'white': '白色',
            'red': '红色',
            'green': '绿色',
            'blue': '蓝色',
            'yellow': '黄色',
            'orange': '橙色',
            'purple': '紫色'
        }
        return color_map.get(color, color if isinstance(color, str) else '自定义')

    def on_style_changed(self, event=None):
        """样式改变时的处理"""
        if not hasattr(self, 'current_edit_index') or self.current_edit_index is None:
            return

        box_item = self.text_boxes[self.current_edit_index]

        # 更新字体大小
        size_text = self.font_size_edit_var.get()
        if size_text == "自动":
            box_item.font_size = None
        else:
            try:
                box_item.font_size = int(size_text)
            except:
                box_item.font_size = None

        # 更新字体
        font_name = self.font_edit_var.get()
        box_item.font_path = self.get_font_path_from_name(font_name)

        # 更新颜色
        color_name = self.color_edit_var.get()
        box_item.text_color = self.get_color_from_name(color_name)

        logging.info(f"更新文本框 #{self.current_edit_index + 1} 样式: 大小={size_text}, 字体={font_name}, 颜色={color_name}")

    def get_font_path_from_name(self, font_name):
        """根据字体名称获取字体路径"""
        font_paths = {
            '默认': None,
            '微软雅黑': 'C:/Windows/Fonts/msyh.ttc',
            '黑体': 'C:/Windows/Fonts/simhei.ttf',
            '宋体': 'C:/Windows/Fonts/simsun.ttc',
            '楷体': 'C:/Windows/Fonts/simkai.ttf',
            'Arial': 'C:/Windows/Fonts/arial.ttf',
            'Times New Roman': 'C:/Windows/Fonts/times.ttf'
        }
        return font_paths.get(font_name, None)

    def get_color_from_name(self, color_name):
        """根据颜色名称获取颜色值"""
        color_values = {
            '自动': None,
            '黑色': 'black',
            '白色': 'white',
            '红色': 'red',
            '绿色': 'green',
            '蓝色': 'blue',
            '黄色': 'yellow',
            '橙色': 'orange',
            '紫色': 'purple'
        }
        return color_values.get(color_name, None)

    def choose_custom_color(self):
        """选择自定义颜色"""
        from tkinter import colorchooser

        if not hasattr(self, 'current_edit_index') or self.current_edit_index is None:
            messagebox.showwarning("警告", "请先选择一个文本框")
            return

        color = colorchooser.askcolor(title="选择文字颜色")
        if color[1]:  # color[1] 是十六进制颜色值
            box_item = self.text_boxes[self.current_edit_index]
            box_item.text_color = color[1]
            self.color_edit_var.set(f"自定义({color[1]})")
            logging.info(f"设置文本框 #{self.current_edit_index + 1} 颜色为: {color[1]}")

    def reset_style(self):
        """重置样式为自动"""
        if not hasattr(self, 'current_edit_index') or self.current_edit_index is None:
            messagebox.showwarning("警告", "请先选择一个文本框")
            return

        box_item = self.text_boxes[self.current_edit_index]
        box_item.font_size = None
        box_item.font_path = None
        box_item.text_color = None

        self.font_size_edit_var.set("自动")
        self.font_edit_var.set("默认")
        self.color_edit_var.set("自动")

        logging.info(f"重置文本框 #{self.current_edit_index + 1} 样式为自动")

    def apply_edit(self):
        """应用编辑（手动调用或回车触发）"""
        if not hasattr(self, 'current_edit_index') or self.current_edit_index is None:
            return

        new_text = self.edit_var.get().strip()
        if not new_text:
            return

        # 更新翻译文本
        box_item = self.text_boxes[self.current_edit_index]

        # 只有内容真的改变了才更新
        if box_item.translated_text != new_text:
            box_item.translated_text = new_text
            # 更新显示
            self.update_display()
            logging.info(f"已修改文本框 #{self.current_edit_index + 1} 的译文: {new_text}")

    def apply_edit_auto(self):
        """自动应用编辑（失去焦点时）"""
        if not hasattr(self, 'current_edit_index') or self.current_edit_index is None:
            return

        new_text = self.edit_var.get().strip()
        if not new_text:
            return

        # 更新翻译文本
        box_item = self.text_boxes[self.current_edit_index]

        # 只有内容真的改变了才更新
        if box_item.translated_text != new_text:
            box_item.translated_text = new_text
            # 更新显示
            self.update_display()

    def select_all(self):
        """全选"""
        for box_item in self.text_boxes:
            box_item.selected = True
        self.update_display()
        logging.info("已全选所有文本框")

    def deselect_all(self):
        """全不选"""
        for box_item in self.text_boxes:
            box_item.selected = False
        self.update_display()
        logging.info("已取消选择所有文本框")

    def invert_selection(self):
        """反选"""
        for box_item in self.text_boxes:
            box_item.selected = not box_item.selected
        self.update_display()
        logging.info("已反选所有文本框")

    def translate_selected(self):
        """翻译选中的文本"""
        if not self.text_boxes:
            messagebox.showwarning("警告", "请先识别文本")
            return

        selected_boxes = [box for box in self.text_boxes if box.selected]
        if not selected_boxes:
            messagebox.showwarning("警告", "请至少选择一个文本框")
            return

        def translate():
            try:
                logging.info(f"正在翻译 {len(selected_boxes)} 个文本框...")
                self.update_config_from_gui()

                translator = Translator(self.config)

                for i, box_item in enumerate(selected_boxes):
                    translated = translator.translate(box_item.text)
                    box_item.translated_text = translated
                    logging.info(f"[{i+1}/{len(selected_boxes)}] '{box_item.text}' -> '{translated}'")

                logging.info("翻译完成!")
                self.root.after(0, self.on_translation_complete)

            except Exception as e:
                logging.error(f"翻译失败: {e}", exc_info=True)
                messagebox.showerror("错误", f"翻译失败: {e}")

        # 在后台线程运行
        thread = threading.Thread(target=translate)
        thread.daemon = True
        thread.start()

    def on_translation_complete(self):
        """翻译完成后的处理"""
        self.update_display()
        self.apply_button.config(state=tk.NORMAL)
        messagebox.showinfo("完成", "翻译完成！点击'应用翻译并保存'生成图片")

    def apply_translation(self):
        """应用翻译并保存图片"""
        if not self.current_image_path:
            return

        try:
            logging.info("正在生成翻译后的图片...")
            self.update_config_from_gui()

            # 直接使用自定义的图像处理逻辑
            result_image = self.render_translated_image()

            # 保存图片
            output_path = self.get_output_path()
            result_image.save(output_path)

            logging.info(f"图片已保存: {output_path}")
            messagebox.showinfo("完成", f"图片已保存至:\n{output_path}")

            # 询问是否打开
            if messagebox.askyesno("打开图片", "是否打开翻译后的图片?"):
                os.startfile(output_path)

        except Exception as e:
            logging.error(f"应用翻译失败: {e}", exc_info=True)
            messagebox.showerror("错误", f"应用翻译失败: {e}")

    def render_translated_image(self):
        """渲染翻译后的图片（支持自定义样式）"""
        from PIL import Image, ImageDraw, ImageFont
        from collections import Counter

        image = Image.open(self.current_image_path)
        draw = ImageDraw.Draw(image)

        for box_item in self.text_boxes:
            # 跳过未选中或没有翻译的文本框
            if not box_item.selected or not box_item.translated_text:
                continue

            coordinates = box_item.coordinates
            translated_text = box_item.translated_text

            # 获取边界框
            x_min = min(p[0] for p in coordinates)
            y_min = min(p[1] for p in coordinates)
            x_max = max(p[0] for p in coordinates)
            y_max = max(p[1] for p in coordinates)

            # 获取背景颜色
            image_processor = ImageProcessor(self.config)
            bg_color = image_processor.get_background_color(image, x_min, y_min, x_max, y_max)

            # 覆盖原文本
            draw.rectangle(((x_min, y_min), (x_max, y_max)), fill=bg_color)

            # 计算字体和位置
            width = x_max - x_min
            height = y_max - y_min

            # 使用自定义样式或自动计算
            if box_item.font_size is not None:
                # 使用指定的字体大小
                font_size = box_item.font_size
                font_path = box_item.font_path or self.config.font_path

                try:
                    font = ImageFont.truetype(font_path, size=font_size)
                except:
                    font = ImageFont.load_default(size=font_size)

                # 计算文字位置（居中）
                bbox = draw.textbbox((0, 0), translated_text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]

                x_offset = (width - text_width) // 2 - bbox[0]
                y_offset = (height - text_height) // 2 - bbox[1]
            else:
                # 自动计算字体大小
                font, x_offset, y_offset = self.calculate_font_size_custom(
                    image, translated_text, width, height, box_item.font_path
                )

            # 确定文字颜色
            if box_item.text_color is not None:
                text_color = box_item.text_color
            else:
                # 自动计算
                text_color = image_processor.get_text_color(bg_color)

            # 绘制翻译文本
            if font:
                draw.text(
                    (x_min + x_offset, y_min + y_offset),
                    translated_text,
                    fill=text_color,
                    font=font
                )

        return image

    def calculate_font_size_custom(self, image, text, width, height, font_path=None):
        """计算合适的字体大小（自定义字体路径）"""
        from PIL import ImageDraw, ImageFont

        draw = ImageDraw.Draw(image)
        font = None
        x, y = 0, 0

        # 使用指定字体路径或默认字体
        if font_path is None:
            font_path = self.config.font_path

        for size in range(1, self.config.max_font_size):
            try:
                new_font = ImageFont.truetype(font_path, size=size)
            except:
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

    def get_output_path(self):
        """生成输出路径"""
        if not self.current_image_path:
            return "output.jpg"

        path = Path(self.current_image_path)
        output_dir = Path(self.config.output_folder)
        output_dir.mkdir(exist_ok=True)

        output_name = f"{path.stem}-translated{path.suffix}"
        return str(output_dir / output_name)

    def swap_languages(self):
        """交换源语言和目标语言"""
        source = self.source_lang_var.get()
        target = self.target_lang_var.get()
        self.source_lang_var.set(target)
        self.target_lang_var.set(source)

    def save_config(self):
        """保存配置到文件"""
        try:
            self.update_config_from_gui()
            self.config.save()
            messagebox.showinfo("成功", "配置已保存到 config.json")
            logging.info("配置已保存")
        except Exception as e:
            messagebox.showerror("错误", f"保存配置失败: {e}")
            logging.error(f"保存配置失败: {e}")

    def update_config_from_gui(self):
        """从GUI更新配置对象"""
        # 更新语言设置
        source_name = self.source_lang_var.get()
        target_name = self.target_lang_var.get()
        self.config.source_language = self.languages_dict.get(source_name, "en")
        self.config.target_language = self.languages_dict.get(target_name, "zh-CN")

        # 更新高级设置
        self.config.ocr_confidence_threshold = self.confidence_var.get()
        self.config.max_font_size = self.font_size_var.get()


def main():
    """主函数"""
    root = tk.Tk()
    app = ImageTranslatorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
