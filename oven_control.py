import time
#import RPi.GPIO as GPIO
"""
#to read temperatures, we need this, according to https://github.com/adafruit/Adafruit_CircuitPython_MAX31855
import adafruit_max31855 
from busio import SPI
from digitalio import DigitalInOut
import board
"""
from threading import Thread, Event
from flask import Flask, request, render_template, redirect
import json

#for testing we use types to create a fake sensor object
import types


class LoopThread(Thread):
    def __init__(self, stop_event, program, sensor):
        self.sensor=sensor
        self.stop_event = stop_event
        self.program = program

        Thread.__init__(self)

    def run(self):
        global ProgramRunning
        global CurrentProgramName
        global CurrentStep
        ProgramRunning=True
        CurrentProgramName=self.program['name']

        #Loop over all steps of the program that was POST-ed in json:
        for settemp, percent, steptime in zip(self.program['temperature'],self.program['percentage'],self.program['time']):
            CurrentStep+=1
            if self.stop_event.is_set():
                break
            oncycles=round(steptime*percent/100*(60/MinimumSecondsPerStep)) #total amount of 30s cycles to keep the oven on (where self.program['time'] contains the time for each step in minutes)
            offcycles=round(steptime*(1-percent/100)*(60/MinimumSecondsPerStep))

            #this piece of code distributes the on and off cycles in equal parts, it's not pretty but it works (technically except for when there is 1 oncycle or 1 offcycle)
            hysteresistemp=settemp
            if oncycles>offcycles & offcycles>0:
                quotient=int(oncycles/offcycles)
                mod=oncycles%offcycles
                for _ in range(offcycles):
                    hysteresistemp=self.ovencycle(settemp,hysteresistemp,(quotient+mod/offcycles),True)
                    hysteresistemp=self.ovencycle(settemp,hysteresistemp,1,False)
                    if self.stop_event.is_set():
                        break
            elif offcycles==0:
                hysteresistemp=self.ovencycle(settemp,hysteresistemp,oncycles,True)
                if self.stop_event.is_set():
                    break
            elif oncycles==0:
                hysteresistemp=self.ovencycle(settemp,hysteresistemp,offcycles,False)
                if self.stop_event.is_set():
                    break
            else:
                quotient=int(offcycles/oncycles)
                mod=offcycles%oncycles
                for i in range(oncycles):
                    hysteresistemp=self.ovencycle(settemp,hysteresistemp,(quotient+mod/oncycles),False)
                    hysteresistemp=self.ovencycle(settemp,hysteresistemp,1,True)
                    if self.stop_event.is_set():
                        break
            time.sleep(2) #TODO: remove me before production
            print('end of program step')
        ProgramRunning=False
        CurrentStep=0
        CurrentProgramName=''
        if self.stop_event.is_set():
            self.stop_event.clear
            
    def ovencycle(self,settemp,hysteresistemp,cycles,ovenon):
        sleeptime=0
        for _ in range(int(cycles*MinimumSecondsPerStep)): #loop over 30s * cycles, while checking each second if we should turn off
            if self.stop_event.is_set():
                break
            curtemp=sensor.temperature
            hightemp = curtemp > hysteresistemp
            if ovenon & hightemp:
                #GPIO.output(18, GPIO.LOW) #set control pin to low, note that currently it is hardcoded to pin 18 **TODO**
                if hysteresistemp>=settemp:
                    hysteresistemp=settemp-1 #set the hysteresis temperature higher than settemp by 1 degree, currently hardcoded TODO
                    print('set hysteresis temp to: '+ str(hysteresistemp))

            elif ovenon:
                #GPIO.output(18, GPIO.HIGH) #set control pin to high, note that currently it is hardcoded to pin 18 **TODO**
                if hysteresistemp<settemp:
                    hysteresistemp=settemp+1
                    print('set hysteresis temp to: '+ str(hysteresistemp))
            else:
                #GPIO.output(18, GPIO.LOW) #set control pin to high, note that currently it is hardcoded to pin 18 **TODO**
                unused=1

            #time.sleep(1) TODO: turn on for production, remove sleeptime variable?
            sleeptime+=1
        
        #Added time for cycle total requiring a step less than 1 second 
        #time.sleep((cycles*MinimumSecondsPerStep-int(cycles*MinimumSecondsPerStep))) TODO: turn on for production, remove sleeptime variable?
        sleeptime+=(cycles*MinimumSecondsPerStep-int(cycles*MinimumSecondsPerStep))
        #GPIO.output(18, GPIO.LOW) #set control pin to low, note that currently it is hardcoded to pin 18 **TODO**
        if ovenon:
            print('oven on for for '+str(sleeptime)+' seconds')
        else:
            print('oven off for for '+str(sleeptime)+' seconds')
        return hysteresistemp

STOP_EVENT = Event()
thread = None


#GPIO.setmode(GPIO.BCM)
#GPIO.setup(18, GPIO.OUT)

"""
#stuff needed for reading the temperature
spi = SPI(clock=board.SCK, MISO=board.MISO, MOSI=board.MOSI)
cs = DigitalInOut(board.D5)
sensor = adafruit_max31855.MAX31855(spi, cs)
"""
#Create a fake sensor: TODO
sensor = types.SimpleNamespace()
sensor.temperature=110

ProgramRunning=False
CurrentProgramName=''
CurrentStep=0

MinimumSecondsPerStep=int(2) #needs to be an int bigger 1

app = Flask(__name__)

@app.route("/stop",methods=["POST"])
def stop():
    STOP_EVENT.set()
    return redirect('/',code=302)

@app.route("/start", methods=["POST"])
def start():
    errors = ""
    if STOP_EVENT.is_set:
        try:
            programjson =request.form["programnumber"]
            program=json.loads(programjson)
        except:
            errors += "<p>{!r} is not valid json.</p>\n".format(request.form["programjson"])
        if not (len(program['percentage'])==program['steps'] & len(program['temperature'])==program['steps'] & len(program['time'])==program['steps']):
            errors +='<p>Invalid program sent, the amount of steps in inconsistent</p>'
        
        if not errors=='':
            return errors
        STOP_EVENT.clear()
        thread = LoopThread(STOP_EVENT, program, sensor)
        thread.start()
    
    return redirect('/',code=302)


@app.route("/")
def home():
    global ProgramRunning
    global CurrentProgramName
    global CurrentStep
    with open('programs.json') as f:
        programs = json.load(f)
    programselect=''
    for program in programs:
        programselect+="<option value='"+json.dumps(programs[program])+"'>"+programs[program]['name']+"</option>\n"
    
    curtemp=sensor.temperature
    if STOP_EVENT.is_set():
        ovenisstopping='The program is currently stopping'
    else:
        ovenisstopping=''
    if ProgramRunning:
        return render_template('Program_running.html',temperature=curtemp,runningprogramname=CurrentProgramName,stepnumber=CurrentStep,ovenisstopping=ovenisstopping)
    else:
        return render_template('No_program_running.html',programlist=programselect,temperature=curtemp)

@app.route("/shutdown")
def shutdown():
    STOP_EVENT.set()
    thread.join()
    return "OK", 200


if __name__ == '__main__':
    app.run()