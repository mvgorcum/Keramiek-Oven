import time
import RPi.GPIO as GPIO
import signal
import sys

#to read temperatures, we need this, according to https://github.com/adafruit/Adafruit_CircuitPython_MAX31855
import adafruit_max31855 
from busio import SPI
from digitalio import DigitalInOut
import board

from threading import Thread, Event
from flask import Flask, request, render_template, redirect
import json

#for testing we use types to create a fake sensor object
#import types

MinimumSecondsPerStep=int(2) #needs to be an int >= 1

gpioOvenPin=23
gpioButtonPin=22

hysteresissize=1

class LoopThread(Thread):
    def __init__(self, stop_event, program, sensor, success_event):
        self.sensor=sensor
        self.stop_event = stop_event
        self.program = program
        self.success_event=success_event

        Thread.__init__(self)

    def run(self):
        global ProgramRunning
        global CurrentProgramName
        global CurrentStep
        global TotalSteps

        ProgramRunning=True
        CurrentProgramName=self.program['name']
        TotalSteps=self.program['steps']
        #Loop over all steps of the program that was POST-ed in json:
        for settemp, percent, steptime in zip(self.program['temperature'],self.program['percentage'],self.program['time']):
            CurrentStep+=1
            if self.stop_event.is_set():
                break
            oncycles=round(steptime*percent/100*(60/MinimumSecondsPerStep)) #total amount of X second cycles to keep the oven on (where self.program['time'] contains the time for each step in minutes)
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
                for _ in range(oncycles):
                    hysteresistemp=self.ovencycle(settemp,hysteresistemp,(quotient+mod/oncycles),False)
                    hysteresistemp=self.ovencycle(settemp,hysteresistemp,1,True)
                    if self.stop_event.is_set():
                        break
            print('end of program step')
        ProgramRunning=False
        CurrentStep=0
        CurrentProgramName=''
        if not self.stop_event.is_set():
            self.success_event.set()
        STOP_EVENT.set()
            
    def ovencycle(self,settemp,hysteresistemp,cycles,ovenon):
        global thermocouplebroken
        thermocouplebroken=False
        thermoerror=0
        sleeptime=0
        for _ in range(int(cycles*MinimumSecondsPerStep)): #loop over 2s * cycles, while checking each second if we should turn off
            if self.stop_event.is_set():
                break
            thermoerror=0
            tempfail=True
            while (thermoerror<50 and tempfail):
                try:
                    curtemp=sensor.temperature
                except:
                    thermoerror+=1
                    tempfail=True
                    print('could not read temperature')
                else:
                    tempfail=False
            if thermoerror>9:
                STOP_EVENT.set()
                print('thermocouple seems broken')
                thermocouplebroken=True
                break
            hightemp = curtemp > hysteresistemp
            if ovenon & hightemp:
                GPIO.output(gpioOvenPin, GPIO.LOW) #set control pin to low
                if hysteresistemp>=settemp:
                    hysteresistemp=settemp-hysteresissize #set the hysteresis temperature higher than settemp by 1 degree, currently hardcoded TODO
                    print('set hysteresis temp to: '+ str(hysteresistemp))

            elif ovenon:
                GPIO.output(gpioOvenPin, GPIO.HIGH) #set control pin to high
                if hysteresistemp<settemp:
                    hysteresistemp=settemp+hysteresissize
                    print('set hysteresis temp to: '+ str(hysteresistemp))
            else:
                GPIO.output(gpioOvenPin, GPIO.LOW) #set control pin to high

            time.sleep(1) 
            sleeptime+=1
        
        #Added time for cycle total requiring a step less than 1 second 
        time.sleep((cycles*MinimumSecondsPerStep-int(cycles*MinimumSecondsPerStep)))
        sleeptime+=(cycles*MinimumSecondsPerStep-int(cycles*MinimumSecondsPerStep))
        GPIO.output(gpioOvenPin, GPIO.LOW) #set control pin to low
        if ovenon:
            print('oven on for for '+str(sleeptime)+' seconds')
        else:
            print('oven off for for '+str(sleeptime)+' seconds')
        return hysteresistemp


STOP_EVENT = Event()
success_event= Event()

thread = None

def stopbutton(channel): # see: https://raspberrypihq.com/use-a-push-button-with-raspberry-pi-gpio/ connect gpioButtonPin to 3.3V, preferably through a resistor
    STOP_EVENT.set()

GPIO.setmode(GPIO.BCM)
GPIO.setup(gpioOvenPin, GPIO.OUT)
GPIO.setup(gpioButtonPin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN) # Set pin to be an input pin and set initial value to be pulled low (off)
GPIO.add_event_detect(gpioButtonPin,GPIO.RISING,callback=stopbutton)


#stuff needed for reading the temperature
spi = SPI(clock=board.SCK, MISO=board.MISO, MOSI=board.MOSI)
cs = DigitalInOut(board.D5)
sensor = adafruit_max31855.MAX31855(spi, cs)

#Create a fake sensor: TODO
#sensor = types.SimpleNamespace()
#sensor.temperature=110

ProgramRunning=False
CurrentProgramName=''
CurrentStep=0



app = Flask(__name__)

@app.route("/home")
def gohome():
    return redirect('/', code=302)

@app.route("/")
def home():
    global thread
    global ProgramRunning
    global CurrentProgramName
    global CurrentStep
    global TotalSteps
    global thermocouplebroken
    with open('programs.json') as f:
        programs = json.load(f)
    programselect=''
    for program in programs:
        programselect+="<option value='"+json.dumps(programs[program])+"'>"+programs[program]['name']+"</option>\n"
    print()
    try:
        curtemp=sensor.temperature
    except:
        curtemp='error reading temperature'
    if STOP_EVENT.is_set():
        ovenisstopping='The program is currently stopping'
    else:
        ovenisstopping=''
    if ProgramRunning:
        if not thread.is_alive():
            if thermocouplebroken:
                return render_template('No_program_running.html',programlist=programselect,temperature=curtemp,threaderror='Thermocouple seems broken')
            else:
                return render_template('No_program_running.html',programlist=programselect,temperature=curtemp,threaderror='program ended unexpectedly')
        else:
            return render_template('Program_running.html',temperature=curtemp,runningprogramname=CurrentProgramName,stepnumber=CurrentStep,totalsteps=TotalSteps,ovenisstopping=ovenisstopping)
    else:
        STOP_EVENT.set()
        if success_event.is_set():
            return render_template('No_program_running.html',programlist=programselect,temperature=curtemp,threaderror='Program ended successfully')
        else:
            return render_template('No_program_running.html',programlist=programselect,temperature=curtemp,threaderror='')

@app.route("/stop",methods=["POST"])
def stop():
    STOP_EVENT.set()
    return redirect('/',code=302)

@app.route("/start", methods=["POST"])
def start():
    global thread
    errors = ""
    if (thread==None or not thread.is_alive()):
        try:
            programjson =request.form["programnumber"]
            program=json.loads(programjson)
        except:
            errors += "<p>{!r} is not valid json.</p>\n".format(request.form["programjson"])
        if not (len(program['percentage'])==program['steps'] & len(program['temperature'])==program['steps'] & len(program['time'])==program['steps']):
            errors +='<p>Invalid program sent, the amount of steps in inconsistent</p>'
        if (max(map(int, program['percentage']))>100):
            errors +='<p>Invalid program sent, Percentage higher than 100</p>'
        if program=='':
            errors +='<p>Empty program sent.</p>'
        if not errors=='':
            return errors
        STOP_EVENT.clear()
        thread = LoopThread(STOP_EVENT, program, sensor, success_event)
        thread.start()
        return redirect('/',code=302)
    else:
        return "A program is already running, cannot start a second one", 409

@app.route("/startpost", methods=["POST"])
def startpost():
    global thread
    errors = ""
    if (thread==None or not thread.is_alive()):
        try:
            program=json.loads(request.data)
        except:
            if len(request.form)>0:
                errors += "<p>{!r} is not valid json.</p>\n".format(request.form["programjson"])
            else:
                return '<p>Empty program sent.</p>'
        if not (len(program['percentage'])==program['steps'] & len(program['temperature'])==program['steps'] & len(program['time'])==program['steps']):
            errors +='<p>Invalid program sent, the amount of steps in inconsistent</p>'
        if (max(map(int, program['percentage']))>100):
            errors +='<p>Invalid program sent, Percentage higher than 100</p>'
        if not errors=='':
            return errors
        STOP_EVENT.clear()
        thread = LoopThread(STOP_EVENT, program, sensor, success_event)
        thread.start()
        return redirect('/',code=302)
    else:
        return "A program is already running, cannot start a second one", 409

@app.route("/createprogram", methods=["POST", "GET"])
def createprogram():
    if request.method == 'POST':
        newprogram=json.loads(request.data)
        with open('programs.json') as f:
            programs = json.load(f)
        #this is not very pretty, but we read the keys in as int to add the new program as the highest number
        programs.update({str(max([int(x) for x in [*programs.keys()]])+1):newprogram})
        if not (len(newprogram['percentage'])==newprogram['steps'] & len(newprogram['temperature'])==newprogram['steps'] & len(newprogram['time'])==newprogram['steps']):
            return "Inconsistent program", 400
        f=open('programs.json','w')
        f.write(json.dumps(programs))
        return "OK", 200

    elif request.method == 'GET':
        return render_template('createProgram.html')

@app.route("/editprogram", methods=["GET","POST"])
def editprogram():
    if request.method == 'POST':
        programwithkey=json.loads(request.form["programnumber"])
        editkey=[*programwithkey.keys()][0]
        program=programwithkey[editkey]
        steps=program['steps']
        programname=program['name']
        stepform=''
        for i in range(1,steps+1):
            stepform += '<tr><td>Stap '+str(i)+'</td><td><input type="number" name="percentage['+str(i)+']" id="percentage['+str(i)+']" Value="'+str(program['percentage'][i-1])+'"></td><td><input type="number" name="temperature['+str(i)+']" id="temperature['+str(i)+']" Value="'+str(program['temperature'][i-1])+'"></td><td><input type="number" name="time['+str(i)+']" id="time['+str(i)+']"  Value="'+str(program['time'][i-1])+'"></td></tr>'
        return render_template('editProgram.html', steps=steps, programname=programname, StepForm=stepform, programid=editkey)
    if request.method == 'GET':
        with open('programs.json') as f:
            programs = json.load(f)
        programselect=''
        for program in programs:
            programselect+="<option value='"+json.dumps({program:programs[program]})+"'>"+programs[program]['name']+"</option>\n"
        return render_template('selecteditProgram.html', programlist=programselect)

@app.route("/updateprogram", methods=["POST"])
def updateprogram():
    toupdateprogram=json.loads(request.data)
    with open('programs.json') as f:
        programs = json.load(f)
    programs.update(toupdateprogram)
    toupdateprogramcontent=toupdateprogram[[*toupdateprogram.keys()][0]]
    if not (len(toupdateprogramcontent['percentage'])==toupdateprogramcontent['steps'] & len(toupdateprogramcontent['temperature'])==toupdateprogramcontent['steps'] & len(toupdateprogramcontent['time'])==toupdateprogramcontent['steps']):
        return "Inconsistent program", 400
    if (max(toupdateprogramcontent['percentage'])>100):
        return "Inconsistent program", 400
    f=open('programs.json','w')
    f.write(json.dumps(programs))
    return "OK", 200

@app.route("/deleteprogram", methods=["POST","GET"])
def deleteprogram():
    if request.method == 'GET':
        with open('programs.json') as f:
            programs = json.load(f)
        programselect=''
        for program in programs:
            programselect+="<option value='"+program+"'>"+programs[program]['name']+"</option>\n"
        return render_template('selectdeleteProgram.html', programlist=programselect)
    if request.method == 'POST':
        programkey=json.loads(request.form["programnumber"])
        with open('programs.json') as f:
            programs = json.load(f)
        deletedprogram=programs.pop(str(programkey), None)
        f=open('programs.json','w')
        f.write(json.dumps(programs))
        return "OK", 200

@app.route("/status")
def status():
    global ProgramRunning
    global CurrentProgramName
    global CurrentStep
    global TotalSteps
    try:
        curtemp=sensor.temperature
    except:
        curtemp='error reading temperature'
    statusobject={"temperature":curtemp}
    if ProgramRunning:
        statusobject.update({"isrunning":True,"currentprogram":CurrentProgramName,"currentstep":CurrentStep,"totalsteps":TotalSteps})
        if STOP_EVENT.is_set():
            statusobject.update({"stopping":True})
    else:
        statusobject.update({"isrunning":False})
    return json.dumps(statusobject)

@app.route("/programs")
def programs():
    with open('programs.json') as f:
        programs = json.load(f)
    return json.dumps(programs)

def Exit_gracefully(signal, frame):
    #turn off the oven pin upon sigint to prevent the oven from accidentally staying on
    GPIO.output(gpioOvenPin, GPIO.LOW)
    sys.exit(0)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, Exit_gracefully)
    app.run()