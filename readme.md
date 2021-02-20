# Ceramics oven controller

This is a python script to run on a raspberry pi to control a ceramics oven from a webbrowser, using flask.

In its current form the temperature sensor is still disabled, and enabling it is untested, however the other parts of the code should be functional.

While this is a cool project, allowing you to create, edit, start and stop a program for an oven from your webbrowser on any generic device, this should *never* be exposed to the internet. Anyone can POST any program to the url and start the oven, no authentication or even maximum temperatures are checked, use at your own risk! I would suggest only running this by using a wifi hotspot created by the raspberry pi, if you decide to use this in production. At the very least make sure that if the device is connected to your network, no ports are forwarded to the device, and all other devices within the network are fully trusted.

To read the temperature we use a Adafruit_MAX31855. We'll try to use [this](https://github.com/adafruit/Adafruit_CircuitPython_MAX31855) python library to read the temperature. See [here](https://learn.adafruit.com/assets/19766) for a connection method.  
