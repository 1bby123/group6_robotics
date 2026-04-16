from vex import *

brain = Brain()

left_drive  = Motor(Ports.PORT6,  GearSetting.RATIO_18_1, False)
right_drive = Motor(Ports.PORT10, GearSetting.RATIO_18_1, True)
arm_motor   = Motor(Ports.PORT3,  GearSetting.RATIO_36_1, False)
claw_motor  = Motor(Ports.PORT4,  GearSetting.RATIO_36_1, False)

WHEEL_DIAMETER_IN = 4.0
DRIVE_SPEED = 20
TURN_SPEED = 15

CLAW_CLOSED = 225

CELL_DIRECTIONS = {
    (2, 1): (20, 105, 16, -17, -93, -22),
    (2, 0): (16, 105, 16, -17, -100, -18),
    (2, 2): (28, 105, 16, -17, -100, -28)
}

def send(msg):
    print(msg)

def drive(inches):
    deg = (inches / (WHEEL_DIAMETER_IN * 3.14159)) * 360
    left_drive.spin_for(FORWARD, deg, DEGREES, DRIVE_SPEED, PERCENT, False)
    right_drive.spin_for(FORWARD, deg, DEGREES, DRIVE_SPEED, PERCENT, True)
    while left_drive.is_spinning() or right_drive.is_spinning():
        wait(20, MSEC)

def turn(deg):
    factor = 2.8
    wheel = deg * factor
    left_drive.spin_for(FORWARD, wheel, DEGREES, TURN_SPEED, PERCENT, False)
    right_drive.spin_for(REVERSE, wheel, DEGREES, TURN_SPEED, PERCENT, True)
    while left_drive.is_spinning() or right_drive.is_spinning():
        wait(20, MSEC)

def stop_all():
    left_drive.stop()
    right_drive.stop()
    arm_motor.stop()
    claw_motor.stop()

def calibrate():
    send("STATUS calibrating")

    arm_motor.spin(FORWARD, 60, PERCENT)
    wait(1500, MSEC)
    arm_motor.stop(HOLD)

    claw_motor.spin(REVERSE, 60, PERCENT)
    wait(1500, MSEC)
    claw_motor.stop(BRAKE)

    arm_motor.set_position(0, DEGREES)
    claw_motor.set_position(0, DEGREES)

    send("STATUS calibrated")

def place(row, col):
    try:
        calibrate()
        send("STATUS placing at (" + str(row) + ", " + str(col) + ")")
        
        arm_motor.spin_to_position(-294, DEGREES, 60, PERCENT, True)
        wait(500, MSEC)

        claw_motor.spin_to_position(CLAW_CLOSED, DEGREES, 100, PERCENT, False)
        wait(1000, MSEC)
        claw_motor.spin(FORWARD, 100, PERCENT)
        wait(300, MSEC)
        claw_motor.stop(HOLD)

        arm_motor.spin_to_position(0, DEGREES, 30, PERCENT, True)

        drive1, turn_deg, drive2, ret_drive2, ret_turn, ret_drive1 = CELL_DIRECTIONS[(row, col)]
        
        drive(drive1)
        turn(turn_deg)
        drive(drive2)

        arm_motor.spin(REVERSE, 20, PERCENT)
        wait(1100, MSEC)
        arm_motor.stop(HOLD)
        
        claw_motor.spin(REVERSE, 20, PERCENT)
        wait(1500, MSEC)
        claw_motor.stop(BRAKE)
        
        arm_motor.spin(FORWARD, 10, PERCENT)
        wait(1500, MSEC)
        arm_motor.stop(HOLD)
        
        drive(ret_drive2)
        turn(ret_turn)
        drive(ret_drive1)

        send("DONE")

    except Exception as e:
        stop_all()
        send("ERROR: " + str(e))

def handle(cmd):
    parts = cmd.strip().split()
    if not parts:
        return

    c = parts[0].upper()

    if c == "PING":
        send("PONG")

    elif c == "HOME":
        calibrate()
        send("DONE")

    elif c == "PLACE" and len(parts) == 3:
        place(int(parts[1]), int(parts[2]))

    elif c == "STOP":
        stop_all()
        send("DONE")

    else:
        send("ERROR")

def main():
    #calibrate()
    #place(2, 1)
    #calibrate()
    #place(2, 0)
    #calibrate()
    #place(2, 2)
    
    send("READY")
    brain.screen.print("READY")

    try:
        s = open('/dev/serial1', 'rb')
    except:
        brain.screen.print("SERIAL FAIL")
        return

    buf = b""

    while True:
        data = s.read(1)

        if not data:
            wait(10, MSEC)
            continue

        if data in (b'\n', b'\r'):
            if buf:
                handle(buf.decode('ascii', 'ignore'))
                buf = b""
        else:
            buf += data

main()