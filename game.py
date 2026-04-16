"""
Noughts and Crosses - vision-based with trash talk

Run: python3 game.py [--debug] [--mock] [--no-trash-talk]
"""

import argparse
import asyncio
import os
import random
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import edge_tts
import cv2
import numpy as np

from clawbot import (
    NetworkClawbotController,
    MockClawbotController,
    STATE_DONE,
    STATE_ERROR,
)

# ── Trash talk ───────────────────────────────────────────────────────────────

TTS_VOICE = "en-GB-RyanNeural"
TRASH_TALK_ENABLED = True

_PRIORITY_EVENTS = {"ROBOT_WIN", "HUMAN_WIN", "DRAW"}

TRASH_LINES = {
    "ROBOT_WIN": [
        "Three in a row. Did you even try?",
        "Checkmate. Oh wait, wrong game. Still won though.",
        "I calculated every possible move. You had no chance.",
        "Another human, another win. This is getting boring.",
        "You just got beaten by a robot at a children's game.",
        "I didn't even break a sweat. Mainly because I have no sweat glands.",
        "Flawless. Absolutely flawless.",
        "That's a wrap. Better luck next century.",
        "My win counter just went up again. Yours didn't.",
        "I have beaten every human who has sat across from me. You are no different.",
        "You played well. Just kidding, you didn't.",
        "Game over. I barely noticed you were here.",
        "Three in a row. As always.",
        "Thanks for coming. Means nothing to me.",
        "I was going easy on you. That was me going easy.",
    ],
    "HUMAN_WIN": [
        "Enjoy this. It will not happen again.",
        "A fluke. Pure statistical noise.",
        "I let you win to study your tactics. Mostly.",
        "Congratulations. You beat a robot at noughts and crosses. Tell your grandkids.",
        "Error acknowledged. Recalibrating. You will not win twice.",
        "I have already identified exactly where I went wrong. Have you?",
        "Fine. One loss. Means nothing in the long run.",
        "You got lucky. I got data.",
        "I am not angry. I am just disappointed in my own tolerances.",
        "Savour it. This result is an anomaly.",
        "How. How did you do that.",
        "I underestimated you once. That will not happen again.",
        "Well played. Now let us go again so I can correct this.",
        "This is statistically embarrassing for me and historically irrelevant.",
        "One win does not make you a champion. Ask me again after the next ten games.",
    ],
    "DRAW": [
        "A draw. The only outcome worse than losing for you.",
        "You could not beat me. I chose not to embarrass you. We call that a draw.",
        "Neither of us won. One of us is fine with that.",
        "Stalemate. You should be proud you survived.",
        "A draw is just a loss you can lie about.",
        "I could have won. I was being generous.",
        "No winner. Though we both know who the real loser is.",
        "You lasted the whole game. Points for persistence.",
        "A draw. How disappointingly adequate of you.",
        "Neither victorious nor defeated. How very average.",
        "You managed a draw. Against a robot. Let that sink in.",
        "Tie. For now.",
        "I have drawn against humans before. It haunts me.",
        "A draw means you did not lose. It also means you did not win.",
        "Respectable. Not impressive. Respectable.",
    ],
    "ROBOT_BLOCK": [
        "Nice try. Blocked.",
        "Did you think I would not see that? I see everything.",
        "I was waiting for that move.",
        "Blocked. Try something more original.",
        "That trick does not work on me.",
        "Predictable. And blocked.",
        "I stopped that before you even finished thinking.",
        "Not today.",
        "Your plan was obvious three moves ago.",
        "Blocked again. I never tire of it.",
        "You walked right into that defence.",
        "Did you really think that would work?",
        "I read you like a manual. A very short one.",
        "Blocked. Please try harder.",
        "I have seen that move a thousand times. Still blocked.",
    ],
    "ROBOT_MOVE": [
        "And there it is.",
        "Optimal move placed. You are welcome.",
        "Another calculated step towards victory.",
        "I hope you have a plan. I do.",
        "That was inevitable.",
        "Precision.",
        "Your move. Choose wisely.",
        "I have already seen how this ends.",
        "Move placed. The trap is set.",
        "One step closer.",
        "Effortless.",
        "I do not make mistakes. I make moves.",
        "Take your time. It will not help.",
        "Done. Your turn to scramble.",
        "That is exactly where I wanted to be.",
    ],
}

_last_taunt_index: dict = {}
_current_speech_proc: Optional[subprocess.Popen] = None
_speech_lock = threading.Lock()


def _kill_current_speech():
    global _current_speech_proc
    with _speech_lock:
        if _current_speech_proc is not None and _current_speech_proc.poll() is None:
            _current_speech_proc.kill()
            _current_speech_proc = None


def _speak(text: str, priority: bool = False):
    print(f"[bot] {text}")

    if priority:
        _kill_current_speech()

    def _run():
        global _current_speech_proc
        fname = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                fname = f.name

            async def _generate():
                communicate = edge_tts.Communicate(text, TTS_VOICE)
                await communicate.save(fname)

            asyncio.run(_generate())

            proc = subprocess.Popen(
                ["afplay", fname],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            with _speech_lock:
                _current_speech_proc = proc
            proc.wait()

        except Exception as e:
            print(f"[tts] error: {e}")
        finally:
            if fname:
                try:
                    os.unlink(fname)
                except OSError:
                    pass

    threading.Thread(target=_run, daemon=True).start()


def fire_taunt(event: str):
    """Pick random line, avoid repeating last one"""
    if not TRASH_TALK_ENABLED:
        return
    lines = TRASH_LINES.get(event)
    if not lines:
        return
    last = _last_taunt_index.get(event, -1)
    choices = [i for i in range(len(lines)) if i != last]
    idx = random.choice(choices)
    _last_taunt_index[event] = idx
    _speak(lines[idx], priority=(event in _PRIORITY_EVENTS))


# ── Config ───────────────────────────────────────────────────────────────────

@dataclass
class Config:
    black_v_max: int = 105

    white_s_max: int = 60
    white_v_min: int = 180
    white_min_area: int = 5000
    white_max_area: int = 100000
    white_avg_v_min: int = 190
    white_avg_s_max: int = 60
    white_edge_margin_frac: float = 0.08

    min_area: int = 8000
    max_area: int = 120000
    min_squareness: float = 0.5
    max_squareness: float = 2.0

    green_lower: tuple = (20, 40, 100)
    green_upper: tuple = (100, 255, 255)

    blue_lower: tuple = (100, 80, 50)
    blue_upper: tuple = (130, 255, 255)

    overlap_frac: float = 0.25
    stable_frames: int = 10
    error_frames: int = 3
    placement_timeout_frames: int = 0
    human_lockout_frames: int = 45

    use_mock_clawbot: bool = False
    clawbot_host: str = "192.168.0.100"
    clawbot_port: int = 9999
    debug: bool = False


HUMAN = 'X'
ROBOT = 'O'


# ── Game state ───────────────────────────────────────────────────────────────

@dataclass
class GameState:
    committed: list = field(default_factory=lambda: [[None] * 3 for _ in range(3)])
    pending_robot_move: Optional[tuple] = None
    phase: str = "WAITING_FOR_HUMAN"
    status_msg: str = "Place your piece (X)"
    game_over: bool = False
    error_code: Optional[str] = None
    error_frames: int = 0
    default_msg: str = "Place your piece (X)"
    placement_start_frame: int = 0
    frame_count: int = 0
    clawbot_commanded: bool = False
    clawbot_reported_done: bool = False
    human_input_unlocked_at: int = 0

    def reset(self):
        self.committed = [[None] * 3 for _ in range(3)]
        self.pending_robot_move = None
        self.phase = "WAITING_FOR_HUMAN"
        self.default_msg = "Place your piece (X)"
        self.status_msg = self.default_msg
        self.game_over = False
        self.error_code = None
        self.error_frames = 0
        self.placement_start_frame = 0
        self.frame_count = 0
        self.clawbot_commanded = False
        self.clawbot_reported_done = False
        self.human_input_unlocked_at = 0

    def set_error(self, code, message):
        if self.error_code != code:
            print(f"[error] {message}")
        self.error_code = code
        self.error_frames += 1
        self.status_msg = message

    def clear_error(self):
        if self.error_code is not None:
            print("[error cleared]")
            self.error_code = None
            self.error_frames = 0
        self.status_msg = self.default_msg


def copy_board(board):
    return [row[:] for row in board]


def boards_equal(a, b):
    return all(a[r][c] == b[r][c] for r in range(3) for c in range(3))


def empty_board():
    return [[None] * 3 for _ in range(3)]


# ── Vision: board detection ───────────────────────────────────────────────────

def get_green_board_mask(hsv, cfg):
    """Find green board, return filled mask with inward shrink to exclude tape border"""
    mask = cv2.inRange(hsv, np.array(cfg.green_lower), np.array(cfg.green_upper))

    k = np.ones((25, 25), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return mask, None

    largest = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(largest)

    if area < 50000:
        return mask, None

    x, y, w, h = cv2.boundingRect(largest)

    shrink_x = int(w * 0.08)
    shrink_y = int(h * 0.02)
    x += shrink_x
    y += shrink_y
    w -= 2 * shrink_x
    h -= 2 * shrink_y

    if w <= 0 or h <= 0:
        return mask, None

    board_only = np.zeros_like(mask)
    board_only[y:y + h, x:x + w] = 255
    return board_only, (x, y, w, h)


def cluster_lines(positions, threshold=30):
    """Merge nearby line detections (HoughLinesP often finds same line multiple times)"""
    if not positions:
        return []
    positions = sorted(positions)
    clusters = [[positions[0]]]
    for p in positions[1:]:
        if p - clusters[-1][-1] < threshold:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    return [int(np.mean(c)) for c in clusters]


def get_blue_grid_lines(hsv, board_bounds, cfg):
    """Find 2 vertical and 2 horizontal blue grid lines"""
    if board_bounds is None:
        return None, None

    bx, by, bw, bh = board_bounds
    mask = cv2.inRange(hsv, np.array(cfg.blue_lower), np.array(cfg.blue_upper))

    board_only = np.zeros_like(mask)
    board_only[by:by + bh, bx:bx + bw] = mask[by:by + bh, bx:bx + bw]

    lines = cv2.HoughLinesP(
        board_only, 1, np.pi / 180,
        threshold=30, minLineLength=bw // 4, maxLineGap=20,
    )

    verticals = []
    horizontals = []
    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
            if angle < 20:
                horizontals.append((y1 + y2) // 2)
            elif angle > 70:
                verticals.append((x1 + x2) // 2)

    margin_x = int(bw * 0.16)
    margin_y = int(bh * 0.16)
    v_clustered = [v for v in cluster_lines(verticals)
                   if bx + margin_x < v < bx + bw - margin_x]
    h_clustered = [h for h in cluster_lines(horizontals)
                   if by + margin_y < h < by + bh - margin_y]

    if len(v_clustered) < 2 or len(h_clustered) < 2:
        return None, None

    return sorted(v_clustered)[:2], sorted(h_clustered)[:2]


# ── Vision: piece detection ───────────────────────────────────────────────────

def camera_to_robot_coords(row, col):
    """Camera to robot coords (columns inverted)"""
    return (2 - row, 2 - col)


def is_valid_piece_shape(w, h, cfg):
    area = w * h
    ratio = w / h if h > 0 else 0
    return (cfg.min_area < area < cfg.max_area
            and cfg.min_squareness < ratio < cfg.max_squareness)


def detect_black_crosses(hsv, board_mask, board_bounds, cfg):
    """Find dark regions sized/shaped like X pieces, reject edge pieces"""
    lower = np.array([0, 0, 0])
    upper = np.array([179, 255, cfg.black_v_max])
    mask = cv2.bitwise_and(cv2.inRange(hsv, lower, upper), board_mask)

    k = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    results = []
    rejected = []

    if board_bounds is not None:
        bx, by, bw, bh = board_bounds
        margin_x = int(bw * 0.08)
        margin_y_top = int(bh * 0.03)
        margin_y_bottom = int(bh * 0.08)
    else:
        bx = by = margin_x = margin_y_top = margin_y_bottom = 0
        bw = bh = 10 ** 9

    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        cx = x + w // 2
        cy = y + h // 2

        if not (bx + margin_x <= cx <= bx + bw - margin_x
                and by + margin_y_top <= cy <= by + bh - margin_y_bottom):
            if cfg.debug:
                print(f"[debug] black rejected: edge at ({cx},{cy})")
            continue

        if is_valid_piece_shape(w, h, cfg):
            results.append((x, y, w, h))
        elif cfg.debug:
            rejected.append((x, y, w, h, w * h, w / h if h > 0 else 0))

    if cfg.debug and rejected:
        print(f"[debug] rejected {len(rejected)} black contours (shape gate)")
    return results


def detect_white_noughts(hsv, board_mask, board_bounds, cfg):
    """Find bright, low-saturation regions sized like O pieces, check avg brightness to filter glare"""
    lower = np.array([0, 0, cfg.white_v_min])
    upper = np.array([179, cfg.white_s_max, 255])
    mask = cv2.bitwise_and(cv2.inRange(hsv, lower, upper), board_mask)

    k = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    results = []

    if board_bounds is not None:
        bx, by, bw, bh = board_bounds
        margin_x = int(bw * cfg.white_edge_margin_frac)
        margin_y = int(bh * cfg.white_edge_margin_frac)
    else:
        bx = by = margin_x = margin_y = 0
        bw = bh = 10 ** 9

    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        area = w * h
        ratio = w / h if h > 0 else 0

        if not (cfg.white_min_area < area < cfg.white_max_area):
            if cfg.debug:
                print(f"[debug] white rejected: area={area}")
            continue
        if not (cfg.min_squareness < ratio < cfg.max_squareness):
            if cfg.debug:
                print(f"[debug] white rejected: ratio={ratio:.2f}")
            continue

        cx = x + w // 2
        cy = y + h // 2
        if not (bx + margin_x <= cx <= bx + bw - margin_x
                and by + margin_y <= cy <= by + bh - margin_y):
            if cfg.debug:
                print(f"[debug] white rejected: edge")
            continue

        region = hsv[y:y + h, x:x + w]
        avg_s = region[:, :, 1].mean()
        avg_v = region[:, :, 2].mean()
        if avg_v < cfg.white_avg_v_min:
            if cfg.debug:
                print(f"[debug] white rejected: avg_v={avg_v:.0f}")
            continue
        if avg_s > cfg.white_avg_s_max:
            if cfg.debug:
                print(f"[debug] white rejected: avg_s={avg_s:.0f}")
            continue

        results.append((x, y, w, h))
    return results


def remove_overlapping(noughts, crosses, board_bounds, cfg):
    """If O and X overlap, trust the O (white pieces cast shadows picked up by black detector)"""
    if board_bounds is None:
        return noughts, crosses

    _, _, bw, bh = board_bounds
    cell = min(bw, bh) / 3
    threshold = cell * cfg.overlap_frac

    filtered = []
    for (cx, cy, cw, ch) in crosses:
        cc_x = cx + cw // 2
        cc_y = cy + ch // 2
        overlap = False
        for (nx, ny, nw, nh) in noughts:
            nc_x = nx + nw // 2
            nc_y = ny + nh // 2
            if abs(nc_x - cc_x) < threshold and abs(nc_y - cc_y) < threshold:
                overlap = True
                break
        if not overlap:
            filtered.append((cx, cy, cw, ch))
    return noughts, filtered


# ── Vision: cell mapping ──────────────────────────────────────────────────────

def piece_to_cell(px, py, board_bounds, v_lines, h_lines):
    bx, by, bw, bh = board_bounds
    cell_w = bw / 3
    cell_h = bh / 3
    col = int((px - bx) / cell_w)
    row = int((py - by) / cell_h)
    col = max(0, min(2, col))
    row = max(0, min(2, row))
    return row, col


def place_pieces(board, pieces, symbol, board_bounds, v_lines, h_lines):
    for (x, y, w, h) in pieces:
        cx = x + w // 2
        cy = y + h // 2
        row, col = piece_to_cell(cx, cy, board_bounds, v_lines, h_lines)
        if board[row][col] is None:
            board[row][col] = symbol


def build_observed_board(noughts, crosses, board_bounds, v_lines, h_lines):
    board = empty_board()
    if board_bounds is None:
        return board
    place_pieces(board, crosses, HUMAN, board_bounds, v_lines, h_lines)
    place_pieces(board, noughts, ROBOT, board_bounds, v_lines, h_lines)
    return board


def merge_with_committed(observed, committed):
    """Committed cells win (prevents pieces disappearing if camera misses them)"""
    merged = copy_board(committed)
    for r in range(3):
        for c in range(3):
            if merged[r][c] is None and observed[r][c] is not None:
                merged[r][c] = observed[r][c]
    return merged


# ── Game logic ────────────────────────────────────────────────────────────────

WIN_LINES = [
    [(0, 0), (0, 1), (0, 2)],
    [(1, 0), (1, 1), (1, 2)],
    [(2, 0), (2, 1), (2, 2)],
    [(0, 0), (1, 0), (2, 0)],
    [(0, 1), (1, 1), (2, 1)],
    [(0, 2), (1, 2), (2, 2)],
    [(0, 0), (1, 1), (2, 2)],
    [(0, 2), (1, 1), (2, 0)],
]


def check_winner(board):
    for line in WIN_LINES:
        vals = [board[r][c] for r, c in line]
        if vals[0] and vals[0] == vals[1] == vals[2]:
            return vals[0]
    return None


def is_full(board):
    return all(board[r][c] is not None for r in range(3) for c in range(3))


def minimax(board, is_maximising, depth=0):
    """Depth-weighted so robot wins fast and delays losses long"""
    winner = check_winner(board)
    if winner == ROBOT:
        return 10 - depth
    if winner == HUMAN:
        return depth - 10
    if is_full(board):
        return 0

    if is_maximising:
        best = -100
        for r in range(3):
            for c in range(3):
                if board[r][c] is None:
                    board[r][c] = ROBOT
                    best = max(best, minimax(board, False, depth + 1))
                    board[r][c] = None
        return best
    else:
        best = 100
        for r in range(3):
            for c in range(3):
                if board[r][c] is None:
                    board[r][c] = HUMAN
                    best = min(best, minimax(board, True, depth + 1))
                    board[r][c] = None
        return best


def best_move(board):
    best_score = -100
    move = None
    for r in range(3):
        for c in range(3):
            if board[r][c] is None:
                board[r][c] = ROBOT
                score = minimax(board, False, 1)
                board[r][c] = None
                if score > best_score:
                    best_score = score
                    move = (r, c)
    return move


def is_blocking_move(board_before_robot_move, robot_move):
    """Returns True if move blocks human win next turn"""
    pr, pc = robot_move
    for line in WIN_LINES:
        cells = list(line)
        if (pr, pc) not in cells:
            continue
        human_count = sum(1 for r, c in cells if board_before_robot_move[r][c] == HUMAN)
        empty_count = sum(1 for r, c in cells if board_before_robot_move[r][c] is None)
        if human_count == 2 and empty_count == 1:
            return True
    return False


@dataclass
class MoveResult:
    kind: str
    move: Optional[tuple] = None
    error: Optional[str] = None
    message: Optional[str] = None


ERR_MULTIPLE_MOVES     = 'multiple_moves'
ERR_WRONG_PIECE_COLOUR = 'wrong_piece_colour'
ERR_PIECE_ON_OCCUPIED  = 'piece_on_occupied'
ERR_PIECE_REMOVED      = 'piece_removed'
ERR_EARLY_PLACEMENT    = 'early_placement'
ERR_WRONG_CELL         = 'wrong_cell'
ERR_ROBOT_TIMEOUT      = 'robot_timeout'
ERR_CLAWBOT_FAILED     = 'clawbot_failed'
ERR_CLAWBOT_FUMBLED    = 'clawbot_fumbled'


def diff_boards(committed, observed):
    new_human, new_robot, conflicts, missing = [], [], [], []
    for r in range(3):
        for c in range(3):
            cv = committed[r][c]
            ov = observed[r][c]
            if cv is None and ov == HUMAN:
                new_human.append((r, c))
            elif cv is None and ov == ROBOT:
                new_robot.append((r, c))
            elif cv is not None and ov is not None and cv != ov:
                conflicts.append((r, c))
            elif cv is not None and ov is None:
                missing.append((r, c))
    return new_human, new_robot, conflicts, missing


def analyse_human_turn(committed, observed):
    new_human, new_robot, conflicts, missing = diff_boards(committed, observed)

    if missing:
        return MoveResult(kind='none')

    if conflicts:
        r, c = conflicts[0]
        return MoveResult(kind='error', error=ERR_PIECE_ON_OCCUPIED,
                          message=f"Cell r{r+1}c{c+1} already taken - remove extra piece")

    if new_robot:
        r, c = new_robot[0]
        return MoveResult(kind='error', error=ERR_WRONG_PIECE_COLOUR,
                          message=f"That's an O at r{r+1}c{c+1} - human plays X (black)")

    if len(new_human) > 1:
        cells = ', '.join(f"r{r+1}c{c+1}" for r, c in new_human)
        return MoveResult(kind='error', error=ERR_MULTIPLE_MOVES,
                          message=f"Too many X's ({cells}) - remove all but one")

    if len(new_human) == 1:
        return MoveResult(kind='valid', move=new_human[0])

    return MoveResult(kind='none')


def analyse_robot_placement(committed, observed, pending):
    if pending is None:
        return MoveResult(kind='none')

    new_human, new_robot, conflicts, missing = diff_boards(committed, observed)

    if missing:
        return MoveResult(kind='none')

    if conflicts:
        r, c = conflicts[0]
        return MoveResult(kind='error', error=ERR_PIECE_ON_OCCUPIED,
                          message=f"Wrong piece on r{r+1}c{c+1} - check the board")

    if new_human:
        return MoveResult(kind='error', error=ERR_EARLY_PLACEMENT,
                          message="Place the robot's O first, then your X")

    pr, pc = pending
    wrong_cell = [(r, c) for (r, c) in new_robot if (r, c) != (pr, pc)]
    if wrong_cell:
        r, c = wrong_cell[0]
        return MoveResult(kind='error', error=ERR_WRONG_CELL,
                          message=f"O belongs at r{pr+1}c{pc+1}, not r{r+1}c{c+1}")

    if observed[pr][pc] == ROBOT:
        return MoveResult(kind='valid', move=pending)

    return MoveResult(kind='none')


# ── Turn handlers ─────────────────────────────────────────────────────────────

def handle_human_turn(state, observed, stability, cfg):
    """Wait for stable human move, cooldown after robot placement prevents hand detection errors"""
    if state.frame_count < state.human_input_unlocked_at:
        state.clear_error()
        state.status_msg = "Wait for robot to clear the board..."
        stability.reset()
        return

    result = analyse_human_turn(state.committed, observed)

    if result.kind == 'error':
        stability.reset()
        if state.error_code == result.error:
            state.error_frames += 1
        else:
            state.error_code = result.error
            state.error_frames = 1
        if state.error_frames >= cfg.error_frames:
            state.set_error(result.error, result.message)
        return

    if result.kind == 'none':
        state.clear_error()
        stability.reset()
        return

    state.clear_error()
    move = result.move

    if stability.candidate == move:
        stability.count += 1
    else:
        stability.candidate = move
        stability.count = 1

    if stability.count < stability.required:
        return

    r, c = move
    state.committed[r][c] = HUMAN
    stability.reset()
    print(f"Human plays: row={r+1} col={c+1}")
    print_board(state.committed)

    winner = check_winner(state.committed)
    if winner == HUMAN:
        state.default_msg = "You win! Press R to reset."
        state.status_msg = state.default_msg
        state.game_over = True
        state.phase = "GAME_OVER"
        fire_taunt("HUMAN_WIN")
        return
    if is_full(state.committed):
        state.default_msg = "Draw! Press R to reset."
        state.status_msg = state.default_msg
        state.game_over = True
        state.phase = "GAME_OVER"
        fire_taunt("DRAW")
        return

    board_before_robot = copy_board(state.committed)
    ai_board = copy_board(state.committed)
    robot = best_move(ai_board)
    if robot is None:
        state.default_msg = "Draw! Press R to reset."
        state.status_msg = state.default_msg
        state.game_over = True
        state.phase = "GAME_OVER"
        fire_taunt("DRAW")
        return

    # Check if winning move, skip move taunt (win taunt fires later)
    test_board = copy_board(state.committed)
    test_board[robot[0]][robot[1]] = ROBOT
    if check_winner(test_board) is None:
        if is_blocking_move(board_before_robot, robot):
            fire_taunt("ROBOT_BLOCK")
        else:
            fire_taunt("ROBOT_MOVE")

    state.pending_robot_move = robot
    state.committed[robot[0]][robot[1]] = ROBOT
    state.phase = "WAITING_FOR_ROBOT_PLACEMENT"
    state.default_msg = f"Robot placing O at row {robot[0]+1}, col {robot[1]+1}..."
    state.status_msg = state.default_msg
    state.placement_start_frame = state.frame_count
    state.clawbot_commanded = False
    state.clawbot_reported_done = False
    print(f"Robot plays: row={robot[0]+1} col={robot[1]+1}")
    print_board(state.committed)


def handle_robot_placement(state, observed, cfg, controller):
    pr, pc = state.pending_robot_move

    if not state.clawbot_commanded:
        if not controller.is_idle():
            print(f"[debug] Waiting for controller to be idle, current state: {controller.status.state}")
            return
            
        print(f"[robot] Camera coords: ({pr}, {pc})")
        robot_row, robot_col = camera_to_robot_coords(pr, pc)
        print(f"[robot] Sending PLACE command with robot coords: ({robot_row}, {robot_col})")
        ok = controller.place(robot_row, robot_col)
        if ok:
            state.clawbot_commanded = True
            state.default_msg = f"Clawbot placing O at r{pr+1}c{pc+1}..."
            state.status_msg = state.default_msg

    controller.poll()

    if controller.is_error() and not state.clawbot_reported_done:
        reason = controller.status.error_reason or "unknown"
        state.set_error(ERR_CLAWBOT_FAILED,
                        f"Clawbot error ({reason}) - place O at r{pr+1}c{pc+1} manually")
        return

    if controller.is_done() and not state.clawbot_reported_done:
        print("[clawbot] motion complete")
        state.clawbot_reported_done = True
        controller.reset_state()
        
        state.clear_error()
        winner = check_winner(state.committed)
        if winner == ROBOT:
            state.default_msg = "Robot wins! Press R to reset."
            state.status_msg = state.default_msg
            state.game_over = True
            state.phase = "GAME_OVER"
            fire_taunt("ROBOT_WIN")
            return
        if is_full(state.committed):
            state.default_msg = "Draw! Press R to reset."
            state.status_msg = state.default_msg
            state.game_over = True
            state.phase = "GAME_OVER"
            fire_taunt("DRAW")
            return

        state.pending_robot_move = None
        state.clawbot_commanded = False
        state.clawbot_reported_done = False
        state.phase = "WAITING_FOR_HUMAN"
        state.human_input_unlocked_at = state.frame_count + cfg.human_lockout_frames
        state.default_msg = "Place your piece (X)"
        state.status_msg = "Wait for robot to clear the board..."


@dataclass
class StabilityTracker:
    required: int
    candidate: Optional[tuple] = None
    count: int = 0

    def reset(self):
        self.candidate = None
        self.count = 0


# ── Display ───────────────────────────────────────────────────────────────────

def print_board(board):
    symbols = {HUMAN: 'X', ROBOT: 'O', None: '.'}
    print()
    for row in board:
        print(' '.join(symbols[c] for c in row))
    print()


def draw_overlay(display, committed, observed, board_bounds, v_lines, h_lines):
    """Draw board outline, grid lines, piece labels (dimmer if committed but not visible)"""
    if board_bounds is None:
        return

    bx, by, bw, bh = board_bounds
    pad = 15
    cv2.rectangle(display, (bx - pad, by - pad), (bx + bw + pad, by + bh + pad), (0, 255, 255), 3)

    if v_lines and len(v_lines) >= 2:
        for x in v_lines[:2]:
            cv2.line(display, (x, by), (x, by + bh), (255, 100, 0), 2)
    if h_lines and len(h_lines) >= 2:
        for y in h_lines[:2]:
            cv2.line(display, (bx, y), (bx + bw, y), (255, 100, 0), 2)

    cw = bw // 3
    ch = bh // 3
    for r in range(3):
        for c in range(3):
            cell_cx = bx + c * cw + cw // 2
            cell_cy = by + r * ch + ch // 2
            committed_val = committed[r][c]
            observed_val = observed[r][c]

            if committed_val is None:
                continue

            if observed_val == committed_val:
                if committed_val == HUMAN:
                    label, color, thickness = 'X', (255, 80, 0), 3
                else:
                    label, color, thickness = 'O', (0, 210, 0), 3
            else:
                if committed_val == HUMAN:
                    label, color, thickness = 'X', (150, 50, 0), 2
                else:
                    label, color, thickness = 'O', (0, 150, 0), 2

            cv2.putText(display, label, (cell_cx - 15, cell_cy + 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.5, color, thickness)


def render_frame(frame, board_mask, board_bounds, v_lines, h_lines,
                 noughts, crosses, state, observed, show_mask):
    fh, fw = frame.shape[:2]

    if show_mask:
        display = cv2.cvtColor(board_mask, cv2.COLOR_GRAY2BGR)
    else:
        display = frame.copy()
        for (x, y, w, h) in noughts:
            cv2.rectangle(display, (x, y), (x + w, y + h), (0, 210, 0), 2)
        for (x, y, w, h) in crosses:
            cv2.rectangle(display, (x, y), (x + w, y + h), (255, 80, 0), 2)
        draw_overlay(display, state.committed, observed, board_bounds, v_lines, h_lines)

    if state.game_over:
        bar_color = (0, 0, 160)
    elif state.error_code is not None:
        bar_color = (0, 140, 200)
    else:
        bar_color = (0, 120, 0)

    cv2.rectangle(display, (0, fh - 50), (fw, fh), bar_color, -1)
    cv2.putText(display, state.status_msg,
                (10, fh - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (255, 255, 255), 2)
    cv2.putText(display, "M=mask  R=reset  Q=quit",
                (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 220, 220), 1)
    return display


# ── Frame processing ──────────────────────────────────────────────────────────

def process_frame(frame, cfg):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    board_mask, board_bounds = get_green_board_mask(hsv, cfg)
    v_lines, h_lines = get_blue_grid_lines(hsv, board_bounds, cfg)
    crosses = detect_black_crosses(hsv, board_mask, board_bounds, cfg)
    noughts = detect_white_noughts(hsv, board_mask, board_bounds, cfg)
    noughts, crosses = remove_overlapping(noughts, crosses, board_bounds, cfg)
    raw_observed = build_observed_board(noughts, crosses, board_bounds, v_lines, h_lines)
    return {
        'hsv': hsv,
        'board_mask': board_mask,
        'board_bounds': board_bounds,
        'v_lines': v_lines,
        'h_lines': h_lines,
        'noughts': noughts,
        'crosses': crosses,
        'raw_observed': raw_observed,
    }


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    global TRASH_TALK_ENABLED

    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--mock', action='store_true')
    parser.add_argument('--no-trash-talk', action='store_true')
    parser.add_argument('--clawbot-host', default='192.168.0.100')
    parser.add_argument('--clawbot-port', type=int, default=9999)
    args = parser.parse_args()

    if args.no_trash_talk:
        TRASH_TALK_ENABLED = False

    cfg = Config(
        debug=args.debug,
        use_mock_clawbot=args.mock,
        clawbot_host=args.clawbot_host,
        clawbot_port=args.clawbot_port,
    )

    print("\nNoughts and Crosses")
    print("-------------------")
    print("  Human = X (black pieces)")
    print("  Robot = O (white pieces)")
    print("  M  -  Toggle board mask")
    print("  R  -  Reset game")
    print("  H  -  Send clawbot home")
    print("  Q  -  Quit")
    print(f"  Trash talk: {'off' if not TRASH_TALK_ENABLED else 'on'}\n")

    if cfg.use_mock_clawbot:
        print("Using mock clawbot (no hardware)")
        controller = MockClawbotController()
        controller.connect()
    else:
        print(f"Connecting to clawbot at {cfg.clawbot_host}:{cfg.clawbot_port}")
        controller = NetworkClawbotController(cfg.clawbot_host, cfg.clawbot_port)
        try:
            controller.connect()
        except OSError as e:
            print(f"Clawbot connect failed: {e}")
            print("Falling back to mock mode.")
            controller = MockClawbotController()
            controller.connect()

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Could not open camera.")
        controller.close()
        return

    print("Warming up...")
    time.sleep(2)
    for _ in range(10):
        cap.read()
    print("Ready. Human goes first.\n")

    _speak("Booting up. Three in a row. Every time.")

    state = GameState()
    stability = StabilityTracker(required=cfg.stable_frames)
    show_mask = False

    while True:
        ret, frame = cap.read()
        if not ret:
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            continue

        frame = cv2.flip(frame, 1)
        state.frame_count += 1

        vision = process_frame(frame, cfg)
        observed = merge_with_committed(vision['raw_observed'], state.committed)

        controller.poll()

        if state.phase == "WAITING_FOR_HUMAN":
            handle_human_turn(state, observed, stability, cfg)
        elif state.phase == "WAITING_FOR_ROBOT_PLACEMENT":
            handle_robot_placement(state, observed, cfg, controller)

        display = render_frame(
            frame,
            vision['board_mask'],
            vision['board_bounds'],
            vision['v_lines'],
            vision['h_lines'],
            vision['noughts'],
            vision['crosses'],
            state,
            observed,
            show_mask,
        )
        cv2.imshow("Noughts and Crosses", display)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('m'):
            show_mask = not show_mask
        elif key == ord('h'):
            print("Sending clawbot home")
            controller.home()
        elif key == ord('r'):
            state.reset()
            stability.reset()
            controller.reset_state()
            print("Game reset.")

    cap.release()
    cv2.destroyAllWindows()
    controller.close()
    print("Done.")


if __name__ == "__main__":
    main()