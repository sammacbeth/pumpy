from __future__ import print_function 
import sys
import serial

def error(*objs):
    print("ERROR: ", *objs, file=sys.stderr)

class Pump:
    def __init__(self,comport,address = 0,verbose = False):
        self.comport = comport;
        self.serialcon = serial.Serial(port = self.comport,stopbits = serial.STOPBITS_TWO,parity = serial.PARITY_NONE,timeout=2)
        self.address = '{0:02.0f}'.format(address)
        self.verbose = verbose
        self.diameter = None
        self.flowrate = None
        self.targetvolume = None

    def __repr__(self):
        string = ''
        for attr in self.__dict__:
            string += '%s: %s\n' % (attr,self.__dict__[attr]) 
        return string

    def setdiameter(self,diameter):
        if diameter > 35 or diameter < 0.1:
            error('Syringe diameter must be between 0.1 and 35 mm')

        diameter = str(diameter)

        # Pump only considers 2 d.p. - anymore are ignored
        if len(diameter) > 5:
            diameter = diameter[0:5]
            diameter = removecrud(diameter)
            print('Warning: diameter truncated to',diameter,'mm')
        else:
            diameter = removecrud(diameter)

        # Send command   
        self.serialcon.write(self.address + 'MMD' + diameter + '\r')
        resp = self.serialcon.read(5)

        # Pump replies with address and status (:, < or >)        
        if resp[-1] == ':' or resp[-1] == '<' or resp[-1] == '>':
            # check if diameter has been set correctlry
            self.serialcon.write(self.address + 'DIA\r')
            resp = self.serialcon.read(15)
            returned_diameter = removecrud(resp[4:9])
            
            # Check diameter was set accurately
            if returned_diameter != diameter:
                error('Set diameter does not match diameter on pump.\n','Set:',diameter,'Returned:',returned_diameter)
            elif returned_diameter == diameter:
                self.diameter = float(returned_diameter)
                if self.verbose:
                     print('Diameter set to',returned_diameter,'mm')
        else:
            error('Pump response not understood.')

    def setflowrate(self,flowrate):
        flowrate = str(flowrate)

        if len(flowrate) > 5:
            flowrate = flowrate[0:5]
            flowrate = removecrud(flowrate)
            print('Warning: flow rate truncated to',flowrate,'uL/min')
        else:
            flowrate = removecrud(flowrate)

        self.serialcon.write(self.address + 'ULM' + flowrate + '\r')
        resp = self.serialcon.read(5)
        
        if resp[-1] == ':' or resp[-1] == '<' or resp[-1] == '>':
            # Flow rate was sent, check it was set correctly
            self.serialcon.write(self.address + 'RAT\r')
            resp = self.serialcon.read(150)
            returned_flowrate = removecrud(resp[2:-5])

            if returned_flowrate != flowrate:
                error('Set flowrate does not match flowrate on pump.\n','Set:',flowrate,'Returned:',returned_flowrate)
            elif returned_flowrate == flowrate:
                self.flowrate = returned_flowrate
                if self.verbose:
                    print('Flow rate set to',returned_flowrate,'uL/min')
        elif 'OOR' in resp:
            error('Flow rate out of range')
        else:
            error('Set flow rate: unexpected response from pump after writing flow rate')
            
    def infuse(self):
        if self.diameter is None:
            error('Diameter not set. Set diameter.')
        elif self.flowrate is None:
            error('Flow rate not set. Set flow rate.')
        else:
            self.serialcon.write(self.address + 'RUN\r')
            resp = self.serialcon.read(5)
            while resp[-1] != '>':
                if resp[-1] == '<': # wrong direction
                    self.serialcon.write(self.address + 'REV\r')
                else:
                    error('Infuse command: unexpected response from pump',resp)
                    break
                resp = self.serialcon.read(5)

            if self.verbose:
                print('Infusing')

    def withdraw(self):
        if self.diameter is None:
            error('Diameter not set. Set diameter.')
        elif self.flowrate is None:
            error('Flow rate not set. Set flow rate.')
        else:
            self.serialcon.write(self.address + 'REV\r')
            resp = self.serialcon.read(5)
            
            while resp[-1] != '<':
                if resp[-1] == ':': # pump not running
                    self.serialcon.write(self.address + 'RUN\r')
                elif resp[-1] == '>': # wrong direction
                    self.serialcon.write(self.address + 'REV\r')
                
                resp = self.serialcon.read(5)
            
            if self.verbose:
                print('Withdrawing')

    def stop(self):
        self.serialcon.write(self.address + 'STP\r')
        resp = self.serialcon.read(5)
        
        if resp[-1] != ':':
            error('Pump not stopped',resp)
        elif self.verbose:
            print('Stopped')

    def settargetvolume(self,targetvolume):
        self.serialcon.write(self.address + 'MLT' + str(targetvolume) + '\r')
        resp = self.serialcon.read(5)

        # response should be XX:, XX>, XX< where XX is address
        resp = resp[-3:] # resp starts with CR/LF/etc, get rid

        if resp[0:2] != self.address:
            error('Response has incorrect address')
        elif resp[-1] == ':' or resp[-1] == '>' or resp[-1] == '<':
            self.targetvolume = float(targetvolume)
            if self.verbose:
                print('Target volume set to',targetvolume,'uL')
    
    def waituntiltarget(self):
        if self.targetvolume is None:
            error('Target volume not set.')
        else:
            # counter - need it to check if it's the first loop
            i = 0
        
            while True:
                # Read once
                self.serialcon.write(self.address + 'VOL\r')
                resp1 = self.serialcon.read(15)

                if ':' in resp1 and i == 0:
                    error('Pump is not infusing/withdrawing. Infuse or withdraw then run waituntiltarget().')
                elif ':' in resp1 and i != 0:
                    # pump has already come to a halt
                    if self.verbose:
                        print('Target volume reached.')
                    break

                # Read again
                self.serialcon.write(self.address + 'VOL\r')
                resp2 = self.serialcon.read(15)

                # Check if they're the same - if they are, break, otherwise continue
                if resp1 == resp2:
                    if self.verbose:
                        print('Target volume reached.')
                    break

                i = i+1
    
    # For debugging
    def close(self):
        self.serialcon.close()

    def clearbuffers(self):
        self.serialcon.flushOutput()
        self.serialcon.flushInput()

def removecrud(string):
    # Remove trailing zeros after decimal places from a string
    if "." in string:
        while string[-1] == '0':
            string = string[0:-1]

    # Remove pointless decimal points
    if string[-1] == ".":
        string = string[:-1]

    # Remove leading spaces
    while string[0] == ' ':
        string = string[1:]

    # Remove trailing spaces
    while string[-1] == ' ':
        string = string[:-2]

    return string