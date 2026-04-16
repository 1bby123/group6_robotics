# Tic-Tac-Toe Robot - Group 6 Robotics Project

## Overview
An autonomous tic-tac-toe playing robot that uses computer vision to detect human moves and plays optimally using the minimax algorithm. The robot physically picks up and places white O pieces on a 3x3 game board while the human plays with black X pieces.

## System Architecture

### Hardware Components
- **VEX EXP Brain** - Controls motors and executes placement commands
- **Raspberry Pi 4** - Acts as TCP/serial relay between Mac and VEX brain
- **Mac with webcam** - Runs computer vision and game logic
- **Motors:**
  - 2x Drive motors (Ports 6, 10) - 18:1 gear ratio
  - 1x Arm motor (Port 3) - 36:1 gear ratio
  - 1x Claw motor (Port 4) - 36:1 gear ratio
- **Game Board** - Green board with blue tape grid lines
- **Game Pieces** - White 3D-printed O pieces, black X pieces

### Software Stack
- **brain.py** - VEX Python code running on the robot
- **pi_server.py** - Python TCP/serial relay on Raspberry Pi
- **game.py** - Main game logic, computer vision, and AI (Mac)
- **clawbot.py** - Network controller interface (Mac)

### Communication Flow
- Mac (game.py)
→ TCP socket →
Raspberry Pi (pi_server.py)
→ USB Serial →
VEX Brain (brain.py)
## Setup Instructions

### Prerequisites
**On Mac:**
```bash
pip install opencv-python numpy edge-tts
```

**On Raspberry Pi:**
```bash
pip install pyserial
```

### Hardware Setup
1. Connect VEX EXP brain to Raspberry Pi via USB
2. Position webcam above the game board looking down
3. Ensure the robot can access the pickup location and all 9 board cells
4. Power on VEX brain and Raspberry Pi

### Network Configuration
1. Connect Raspberry Pi to the same network as Mac
2. Find Pi's IP address: `hostname -I` (on Pi)
3. Note the IP for game.py configuration

## Running the System

### 1. Start the Pi Server (on Raspberry Pi)
```bash
python3 pi_server.py
```
Expected output:
[brain] connected on /dev/ttyACM0 @ 115200
[server] listening on 0.0.0.0:9999

### 2. Upload and Run VEX Code
- Upload `brain.py` to VEX EXP brain using VEXcode
- Run the program on the brain
- Brain will calibrate, then display "READY"

### 3. Start the Game (on Mac)
```bash
python3 game.py --clawbot-host <PI_IP_ADDRESS>
```
Replace `<PI_IP_ADDRESS>` with your Pi's IP (e.g., `192.168.1.42`)

Optional flags:
- `--mock` - Run without hardware (simulates robot responses)
- `--no-trash-talk` - Disable text-to-speech commentary
- `--debug` - Enable vision debugging output

## How It Works

### Computer Vision
1. **Board Detection** - Detects green board using HSV color filtering
2. **Grid Line Detection** - Finds blue tape grid lines using Hough Line Transform
3. **Piece Detection:**
   - Black X pieces: Low V-channel values (dark objects)
   - White O pieces: High V-channel, low saturation (bright white objects)
4. **Cell Mapping** - Maps detected pieces to 3x3 grid coordinates

### Game Logic
1. **Human Turn:**
   - Camera detects stable X placement (must be stable for 10 frames)
   - Validates move (correct piece color, not occupied, single piece)
   - Commits move to game state

2. **Robot Turn:**
   - Calculates optimal move using minimax algorithm
   - Sends `PLACE row col` command through Pi to VEX brain
   - Robot executes: calibrate → pickup → navigate → drop → return
   - Waits for `DONE` confirmation before continuing

3. **Win Detection:**
   - Checks for three-in-a-row after each move
   - Announces winner or draw

### Robot Movement
The VEX brain receives coordinates in format `PLACE row col` where:
- Row: 0-2 (top to bottom from robot's perspective)
- Col: 0-2 (left to right from robot's perspective)

**Note:** Camera coordinates are inverted (rotated 180°) from robot coordinates. The `camera_to_robot_coords()` function handles this translation.

**Calibrated cells** (currently only row 2 is calibrated):
- (2, 0): Drive 16", turn 105°, drive 16", return optimized
- (2, 1): Drive 20", turn 105°, drive 16", return optimized  
- (2, 2): Drive 28", turn 105°, drive 16", return optimized

## Error Handling

### Vision Errors
- **Multiple pieces detected** - Asks user to remove extras
- **Wrong piece color** - Detects O when expecting X
- **Piece on occupied cell** - Validates cells aren't already taken
- **Edge detection** - Rejects pieces too close to board edge (prevents robot arm misdetection)

### Robot Errors
- **Clawbot connection failure** - Falls back to mock mode
- **Serial communication error** - Logged and reported
- **Movement timeout** - Configurable timeout for piece placement
- **Grip failure** - Robot calibrates before each move to ensure consistent pickup

### Recovery
- Press `R` to reset game state
- Press `H` to send robot to home position
- All errors are logged to console with timestamps

## Keyboard Controls
- `M` - Toggle board mask view (shows vision processing)
- `R` - Reset game
- `H` - Send robot to home position (calibrate)
- `Q` - Quit application

## File Structure
.
├── brain.py          # VEX robot control code
├── game.py           # Main game logic and vision
├── clawbot.py        # Network controller interface
├── pi_server.py      # Raspberry Pi TCP/serial relay
└── README.md         # This file


## Calibration

### Board Detection Tuning
Adjust HSV ranges in `game.py` Config class:
```python
green_lower: tuple = (20, 40, 100)  # Board color
green_upper: tuple = (100, 255, 255)
blue_lower: tuple = (100, 80, 50)   # Grid lines
blue_upper: tuple = (130, 255, 255)
```

### Robot Movement Calibration
In `brain.py`, update `CELL_DIRECTIONS` dictionary:
```python
CELL_DIRECTIONS = {
    (row, col): (drive1, turn_deg, drive2, ret_drive2, ret_turn, ret_drive1)
}
```

Run calibration for each cell:
1. Test movement to cell
2. Adjust drive distances and turn angles
3. Test return path
4. Record values in dictionary

## Known Limitations
- Only row 2 (bottom row from camera view, top row from robot view) is currently calibrated
- Requires good lighting conditions for reliable piece detection
- Camera must remain stationary during gameplay
- Pieces must remain visible (not occluded by hands)

## Future Improvements
- Calibrate all 9 cells for full board coverage
- Add automatic board calibration on startup
- Implement multi-game statistics tracking
- Add difficulty levels (intentional sub-optimal moves)
- Support for different board sizes

## References

### Libraries & Tools
- OpenCV: https://opencv.org/
- NumPy: https://numpy.org/
- edge-tts: https://github.com/rany2/edge-tts
- PySerial: https://pyserial.readthedocs.io/

### Algorithms
- Minimax algorithm: https://en.wikipedia.org/wiki/Minimax
- Hough Line Transform: https://docs.opencv.org/4.x/d9/db0/tutorial_hough_lines.html
- HSV color space: https://docs.opencv.org/4.x/df/d9d/tutorial_py_colorspaces.html

### VEX Robotics
- VEXcode Python API: https://api.vexcode.cloud/v5/
- VEX EXP Documentation: https://www.vexrobotics.com/exp

### AI Assistance
AI was used throughout development for:
- Algorithm implementation (minimax, computer vision)
- Debugging motor control and coordinate systems
- Network communication protocols

**AITS Level: 4 - AI for Enhancing**

AI was used extensively throughout development but all critical decisions, architecture choices, calibration values, and integration work were human-directed. The human developers:
- Designed the overall system architecture
- Debugged and calibrated all robot movements
- Tuned computer vision parameters through testing
- Integrated hardware components
- Made all design decisions about game flow and error handling
- Critically reviewed and tested all AI-generated code

## Team
Group 6 - Sheffield Hallam University  
Module: 55-608216 Robotics (Level 6)  
Submission: April 2026

## License
Educational project - Sheffield Hallam University
