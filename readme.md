# Ceramics oven controller

This is a python script to run on a raspberry pi to control a ceramics oven.

We'll try to get it to run in a browser, using flask, roughly following [this](https://blog.pythonanywhere.com/169/) tutorial.  
To read the temperature we use a Adafruit_MAX31855. We'll try to use [this](https://github.com/adafruit/Adafruit_CircuitPython_MAX31855) python library to read the temperature. See [here](https://learn.adafruit.com/assets/19766) for a connection method.  
We'll try to use the GPIO lib to control the oven by setting an output to high or low.
