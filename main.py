from PIL import Image, ImageDraw, ImageFont
from deep_translator import GoogleTranslator
import os, easyocr


def perform_ocr(image_path, reader):
    # Perform OCR on the image
    result = reader.readtext(image_path, width_ths = 0.8,  decoder = 'wordbeamsearch')

    # Extract text and bounding boxes from the OCR result
    extracted_text_boxes = [(entry[0], entry[1]) for entry in result if entry[2] > 0.4]

    return extracted_text_boxes


def get_font(image, text, width, height):

    # Default values at start
    font_size = None  # For font size
    font = None  # For object truetype with correct font size
    box = None  # For version 8.0.0
    x = 0
    y = 0

    draw = ImageDraw.Draw(image)  # Create a draw object

    # Test for different font sizes
    for size in range(1, 500):

        # Create new font
        new_font = ImageFont.load_default(size=font_size)

        # Calculate bbox for version 8.0.0
        new_box = draw.textbbox((0, 0), text, font=new_font)

        # Calculate width and height
        new_w = new_box[2] - new_box[0]  # Bottom - Top
        new_h = new_box[3] - new_box[1]  # Right - Left

        # If too big then exit with previous values
        if new_w > width or new_h > height:
            break

        # Set new current values as current values
        font_size = size
        font = new_font
        box = new_box
        w = new_w
        h = new_h

        # Calculate position (minus margins in box)
        x = (width - w) // 2 - box[0]  # Minus left margin
        y = (height - h) // 2 - box[1]  # Minus top margin

    return font, x, y


def add_discoloration(color, strength):
    # Adjust RGB values to add discoloration
    r, g, b = color
    r = max(0, min(255, r + strength))  # Ensure RGB values are within valid range
    g = max(0, min(255, g + strength))
    b = max(0, min(255, b + strength))
    
    if r == 255 and g == 255 and b == 255:
        r, g, b = 245, 245, 245

    return (r, g, b)


def get_background_color(image, x_min, y_min, x_max, y_max):
    # Define the margin for the edges
    margin = 10

    # Crop a small region around the edges of the bounding box
    edge_region = image.crop(
        (
            max(x_min - margin, 0),
            max(y_min - margin, 0),
            min(x_max + margin, image.width),
            min(y_max + margin, image.height),
        )
    )

    # Find the most common color in the cropped region
    edge_colors = edge_region.getcolors(edge_region.size[0] * edge_region.size[1])
    background_color = max(edge_colors, key=lambda x: x[0])[1]

    # Add a bit of discoloration to the background color
    background_color = add_discoloration(background_color, 40)

    return background_color


def get_text_fill_color(background_color):
    # Calculate the luminance of the background color
    luminance = (
        0.299 * background_color[0]
        + 0.587 * background_color[1]
        + 0.114 * background_color[2]
    ) / 255

    # Determine the text color based on the background luminance
    if luminance > 0.5:
        return "black"  # Use black text for light backgrounds
    else:
        return "white"  # Use white text for dark backgrounds


def replace_text_with_translation(image_path, translated_texts, text_boxes):
    # Open the image
    image = Image.open(image_path)
    draw = ImageDraw.Draw(image)

    # Load a font
    font = ImageFont.load_default()

    # Replace each text box with translated text
    for text_box, translated in zip(text_boxes, translated_texts):

        if translated is None:
            continue

        # Set initial values
        x_min, y_min = text_box[0][0][0], text_box[0][0][1]
        x_max, y_max = text_box[0][0][0], text_box[0][0][1]

        for coordinate in text_box[0]:

            x, y = coordinate

            if x < x_min:
                x_min = x
            elif x > x_max:
                x_max = x
            if y < y_min:
                y_min = y
            elif y > y_max:
                y_max = y

        # Find the most common color in the text region
        background_color = get_background_color(image, x_min, y_min, x_max, y_max)

        # Draw a rectangle to cover the text region with the original background color
        draw.rectangle(((x_min, y_min), (x_max, y_max)), fill=background_color)

        # Calculate font size, box
        font, x, y = get_font(image, translated, x_max - x_min, y_max - y_min)

        # Draw the translated text within the box
        draw.text(
            (x_min + x, y_min + y),
            translated,
            fill=get_text_fill_color(background_color),
            font=font,
        )

    return image


# Initialize the OCR reader
reader = easyocr.Reader(["ch_sim", "en"], model_storage_directory = 'model')

# Initialize the Translator
translator = GoogleTranslator(source="zh-CN", target="en")

# Define input and output location
input_folder = "input"
output_folder = "output"

# Process each image file from input
files = os.listdir(input_folder)
image_files = [file for file in files if file.endswith((".jpg", ".jpeg", ".png"))]
for filename in image_files:
    
    print(f'[INFO] Processing {filename}...')

    image_path = os.path.join(input_folder, filename)

    # Extract text and location
    extracted_text_boxes = perform_ocr(image_path, reader)

    # Translate texts
    translated_texts = []
    for text_box, text in extracted_text_boxes:
        translated_texts.append(translator.translate(text))

    # Replace text with translated text
    image = replace_text_with_translation(image_path, translated_texts, extracted_text_boxes)

    # Save modified image
    base_filename, extension = os.path.splitext(filename)
    output_filename = f"{base_filename}-translated{extension}"
    output_path = os.path.join(output_folder, output_filename)
    image.save(output_path)

    print(f'[INFO] Saved as {output_filename}...')
