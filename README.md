# Image Translator

This project utilizes optical character recognition (OCR) and translation to translate text within images from one language to another. It performs the following steps:

1. **OCR Processing:** The project extracts text and its bounding boxes from input images using the EasyOCR library.
2. **Translation:** It translates the extracted text using the Google Translator API.
3. **Text Replacement:** The translated text is then overlaid onto the image, replacing the original text while maintaining its position and style.
4. **Output:** Finally, the modified image with translated text is saved to an output folder.

## Setup

### Installation

1. Clone this repository to your local machine.
2. Install the required Python dependencies using `pip install pipenv && pipenv install`.

## Usage

1. Place your input images in the `input` folder.
2. Run the script `main.py`.
3. Translated images will be saved in the `output` folder.

## Notes

-   Supported languages for OCR can be seen [here](https://www.jaided.ai/easyocr/)
-   Supported languages for Google Translate can be obtained using the following code:
    ```python
    from deep_translator.constants import GOOGLE_LANGUAGES_TO_CODES
    print(GOOGLE_LANGUAGES_TO_CODES)
    ```
-   Adjustments to text languages, recognition thresholds, translation services, or image processing parameters can be made within the script.

## Examples

![image-1](https://github.com/boysugi20/python-image-translator/assets/53815726/cc2a52b3-2627-4f08-a428-c0dba4341bda)
![image-1-translated](https://github.com/boysugi20/python-image-translator/assets/53815726/3ecafe2e-df19-4ca2-aeff-b05cc89394db)


## Acknowledgments

-   [EasyOCR](https://github.com/JaidedAI/EasyOCR) - For OCR processing.
-   [Google Translator](https://pypi.org/project/deep-translator/) - For text translation.
-   [Pillow (PIL Fork)](https://python-pillow.org/) - For image manipulation.
