from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306
from PIL import ImageDraw, ImageFont, Image
import sys

# Get text from argument
text = sys.argv[1]

# Initialize OLED
serial = i2c(port=1, address=0x3C)
device = ssd1306(serial)

# Create blank image
image = Image.new("1", (device.width, device.height))
draw = ImageDraw.Draw(image)

# Load default font
font = ImageFont.load_default()

# Draw text
draw.text((0, 0), text, font=font, fill=255)

# Display
device.display(image)