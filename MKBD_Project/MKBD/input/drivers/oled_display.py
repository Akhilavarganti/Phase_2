import board
import busio
import textwrap
import adafruit_ssd1306
from PIL import Image, ImageDraw, ImageFont

 

class OLEDDisplay:
    def __init__(self, config):
        self.i2c = busio.I2C(board.SCL, board.SDA)
        self.display = adafruit_ssd1306.SSD1306_I2C(config['width'], config['height'], self.i2c)
        self.width = self.display.width
        self.height = self.display.height
        self.image = Image.new("1", (self.width, self.height))
        self.draw = ImageDraw.Draw(self.image)
        self.font = ImageFont.load_default()
        self.clear()

    def clear(self):
        self.draw.rectangle((0, 0, self.width, self.height), outline=0, fill=0)
        self.display.image(self.image)
        self.display.show()

    def display_text(self, text, line=0):
        self.clear()
        self.draw.text((0, line), text, font=self.font, fill=255)
        self.display.image(self.image)
        self.display.show()

    def display_centered_text(self, text):
            self.clear()
            lines = text.split('\n')
            
            line_height = self.draw.textbbox((0, 0), "A", font=self.font)[3]
            total_text_height = line_height * len(lines)
            y_offset = (self.height - total_text_height) // 2
            
            for i, line in enumerate(lines):
                bbox = self.draw.textbbox((0, 0), line, font=self.font)
                line_width = bbox[2] - bbox[0]
                x = (self.width - line_width) // 2
                y = y_offset + i * line_height
                self.draw.text((x, y), line, font=self.font, fill=255)
            
            self.display.image(self.image)
            self.display.show()
            
   
    

               

