# Ceramics oven controller

This is a python script to run on a raspberry pi to control a ceramics oven, using flask.

Still very much a Work In Progress, running it in its current state won't actually do anything.

To read the temperature we use a Adafruit_MAX31855. We'll try to use [this](https://github.com/adafruit/Adafruit_CircuitPython_MAX31855) python library to read the temperature. See [here](https://learn.adafruit.com/assets/19766) for a connection method.  
