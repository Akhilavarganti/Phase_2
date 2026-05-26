import RPi.GPIO as GPIO
import time

class ButtonInput:
    def __init__(self, pins):
        self.pins = pins
        GPIO.setmode(GPIO.BCM)
        for pin in self.pins:
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    def wait_for_press(self):
        while True:
            for i, pin in enumerate(self.pins):
                if GPIO.input(pin) == GPIO.LOW:
                    time.sleep(0.2)
                    return i
