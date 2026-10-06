#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""stratego-lite —— 简化版陆军棋（原创小项目，纯标准库）。

规则（简化）：
- 6x6 棋盘，中央 2x2 为湖泊（不可进入）。
- 每方 12 枚棋子，随机布于己方底线两行：
  1 元帅、2 将军、3 上校、4 上尉 x2、5 中尉 x2、6 少尉、
  9 侦察兵（可沿直线走任意格，不可跳子）、S 间谍、B 炸弹、F 军旗。
- 棋子军衔对敌方隐藏，交战后双方公开参战棋子。
- 走子：每次沿横/竖走一格（侦察兵可走多格）；炸弹与军旗不可移动。
- 交战：数字小者胜（1 最强）；同级则同归于尽；
  间谍主动进攻元帅时获胜，其余情况间谍必败；
  进攻炸弹者阵亡（本简化版无工兵）；夺取军旗者直接获胜。
- 胜负：夺取对方军旗，或使对方无可走棋子；400 半回合未分胜负判和棋。
"""

import argparse
import random
import sys

ROWS = COLS = 6
LAKES = frozenset({(2, 2), (2, 3), (3, 2), (3, 3)})
SETUP_RANKS = ["1", "2", "3", "4", "4", "5", "5", "6", "9", "S", "B", "F"]
IMMOBILE = frozenset({"B", "F"})
RANK_VALUE = {"1": 10, "2": 9, "3": 8, "4": 6, "5": 5,
              "6": 4, "9": 3, "S": 7, "B": 6, "F": 100}
RANK_NAME = {"1": "元帅", "2": "将军", "3": "上校", "4": "上尉",
             "5": "中尉", "6": "少尉", "9": "侦察兵",
             "S": "间谍", "B": "炸弹", "F": "军旗"}
PLAYER_NAME = ["红方", "蓝方"]
MAX_HALF_MOVES = 400
DIRS = [(-1, 0), (1, 0), (0, -1), (0, 1)]


class IllegalMove(Exception):
    """非法走法。"""


class Piece:
    __slots__ = ("owner", "rank", "revealed")

    def __init__(self, owner, rank):
        self.owner = owner      # 0 红方 / 1 蓝方
        self.rank = rank        # 见 RANK_NAME
        self.revealed = False   # 是否已在交战中公开


def combat(att_rank, dfn_rank):
    """结算交战。返回 'att'（攻方胜）/ 'dfn'（守方胜）/ 'both'（同归于尽）。"""
    if dfn_rank == "F":
        return "att"
    if dfn_rank == "B":
        return "dfn"
    if att_rank == "S":
        return "att" if dfn_rank == "1" else "dfn"
    if dfn_rank == "S":
        return "att"
    a, d = int(att_rank), int(dfn_rank)
    if a < d:
        return "att"
    if a > d:
        return "dfn"
    return "both"


class Game:
    def __init__(self):
        self.board = [[None] * COLS for _ in range(ROWS)]
        self.winner = None  # None / 0 / 1 / 'draw'
        self.half_moves = 0

    # ---------- 局面 ----------
    def piece_at(self, r, c):
        return self.board[r][c]

    def has_movable(self, player):
        for r in range(ROWS):
            for c in range(COLS):
                p = self.board[r][c]
                if p is not None and p.owner == player and p.rank not in IMMOBILE:
                    return True
        return False

    def avg_unrevealed_value(self, player):
        vals = [RANK_VALUE[p.rank] for r in range(ROWS) for c in range(COLS)
                for p in [self.board[r][c]]
                if p is not None and p.owner == player and not p.revealed]
        return sum(vals) / len(vals) if vals else 0.0

    # ---------- 走法 ----------
    def _enterable(self, r, c, player):
        if not (0 <= r < ROWS and 0 <= c < COLS):
            return False
        if (r, c) in LAKES:
            return False
        p = self.board[r][c]
        return p is None or p.owner != player

    def legal_moves(self, player):
        moves = []
        for r in range(ROWS):
            for c in range(COLS):
                p = self.board[r][c]
                if p is None or p.owner != player or p.rank in IMMOBILE:
                    continue
                if p.rank == "9":  # 侦察兵：直线任意格
                    for dr, dc in DIRS:
                        nr, nc = r + dr, c + dc
                        while self._enterable(nr, nc, player):
                            moves.append(((r, c), (nr, nc)))
                            if self.board[nr][nc] is not None:
                                break
                            nr += dr
                            nc += dc
                else:
                    for dr, dc in DIRS:
                        nr, nc = r + dr, c + dc
                        if self._enterable(nr, nc, player):
                            moves.append(((r, c), (nr, nc)))
        return moves

    def apply_move(self, move, player):
        """执行走法，返回战报 dict。非法走法抛 IllegalMove。"""
        (r1, c1), (r2, c2) = move
        if not (0 <= r1 < ROWS and 0 <= c1 < COLS and
                0 <= r2 < ROWS and 0 <= c2 < COLS):
            raise IllegalMove("走法越界")
        att = self.board[r1][c1]
        if att is None or att.owner != player:
            raise IllegalMove("起点没有你的棋子")
        if att.rank in IMMOBILE:
            raise IllegalMove("炸弹/军旗不可移动")
        if (r2, c2) in LAKES:
            raise IllegalMove("不可进入湖泊")
        dfn = self.board[r2][c2]
        if dfn is not None and dfn.owner == player:
            raise IllegalMove("不可吃自己的棋子")
        dr, dc = r2 - r1, c2 - c1
        if att.rank == "9":
            if not ((dr == 0) != (dc == 0)):
                raise IllegalMove("侦察兵只能直线走")
            step_r = 0 if dr == 0 else (1 if dr > 0 else -1)
            step_c = 0 if dc == 0 else (1 if dc > 0 else -1)
            nr, nc = r1 + step_r, c1 + step_c
            while (nr, nc) != (r2, c2):
                if self.board[nr][nc] is not None:
                    raise IllegalMove("侦察兵不可跳子")
                nr += step_r
                nc += step_c
        else:
            if abs(dr) + abs(dc) != 1:
                raise IllegalMove("每次只能走一格")

        report = {"from": (r1, c1), "to": (r2, c2),
                  "attacker": att.rank, "defender": dfn.rank if dfn else None,
                  "outcome": None}
        self.board[r1][c1] = None
        if dfn is None:
            self.board[r2][c2] = att
        else:
            outcome = combat(att.rank, dfn.rank)
            att.revealed = True
            dfn.revealed = True
            report["outcome"] = outcome
            if dfn.rank == "F":
                self.board[r2][c2] = att
                self.winner = player
            elif outcome == "att":
                self.board[r2][c2] = att
            elif outcome == "dfn":
                pass  # 攻方阵亡，守方留在原地
            else:  # both
                self.board[r2][c2] = None
        self.half_moves += 1
        if self.winner is None:
            foe = 1 - player
            if not self.has_movable(foe) or not self.legal_moves(foe):
                self.winner = player
        if self.winner is None and self.half_moves >= MAX_HALF_MOVES:
            self.winner = "draw"
        return report


def new_game(rng):
    g = Game()
    for player, rows in ((1, (0, 1)), (0, (4, 5))):
        ranks = SETUP_RANKS[:]
        rng.shuffle(ranks)
        i = 0
        for r in rows:
            for c in range(COLS):
                g.board[r][c] = Piece(player, ranks[i])
                i += 1
    return g


# ---------- AI ----------
def score_move(game, player, move, rng):
    (r1, c1), (r2, c2) = move
    att = game.board[r1][c1]
    dfn = game.board[r2][c2]
    s = rng.random() * 0.5
    # 向敌方底线推进
    s += (r1 - r2) * 0.15 if player == 0 else (r2 - r1) * 0.15
    if att.rank == "9":
        s += 0.3  # 侦察兵探路
    if dfn is not None:
        att_v = RANK_VALUE[att.rank]
        if dfn.rank == "F":
            return 1e9
        if dfn.revealed:
            outcome = combat(att.rank, dfn.rank)
            dfn_v = RANK_VALUE[dfn.rank]
            if outcome == "att":
                s += dfn_v * 2
            elif outcome == "dfn":
                s -= att_v * 2
            else:
                s += dfn_v - att_v
        else:
            avg = game.avg_unrevealed_value(1 - player)
            s += (avg - att_v) * 0.8
            if att.rank == "9":
                s += 1.0  # 侦察兵试探成本低
    return s


def ai_choose(game, player, rng):
    moves = game.legal_moves(player)
    if not moves:
        return None
    scored = [(score_move(game, player, m, rng), rng.random(), m) for m in moves]
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return scored[0][2]


def play_game(seed, verbose=False):
    rng = random.Random(seed)
    game = new_game(rng)
    player = 0
    while game.winner is None:
        move = ai_choose(game, player, rng)
        if move is None:
            game.winner = 1 - player
            break
        report = game.apply_move(move, player)
        if verbose:
            print(describe_report(game, report, player))
        player = 1 - player
    return game


def describe_report(game, report, player):
    a = RANK_NAME[report["attacker"]]
    (r1, c1), (r2, c2) = report["from"], report["to"]
    s = f"{PLAYER_NAME[player]} {sq(r1, c1)}->{sq(r2, c2)} {a}"
    if report["defender"] is not None:
        d = RANK_NAME[report["defender"]]
        o = report["outcome"]
        word = {"att": "攻方胜", "dfn": "守方胜", "both": "同归于尽"}[o]
        s += f" 交战 {d}：{word}"
    return s


# ---------- 显示 ----------
def sq(r, c):
    return f"{chr(ord('a') + c)}{ROWS - r}"


def parse_sq(text):
    text = text.strip().lower()
    if len(text) != 2 or text[0] not in "abcdef" or text[1] not in "123456":
        raise IllegalMove("坐标格式如 b2")
    return ROWS - int(text[1]), ord(text[0]) - ord("a")


def render(game, viewer):
    lines = ["   " + " ".join("abcdef")]
    for r in range(ROWS):
        row = [f"{ROWS - r} "]
        for c in range(COLS):
            if (r, c) in LAKES:
                row.append("～")
                continue
            p = game.board[r][c]
            if p is None:
                row.append("·")
            elif p.owner == viewer:
                row.append(p.rank)
            else:
                row.append(p.rank if p.revealed else "?")
        row.append(f" {ROWS - r}")
        lines.append(" ".join(row))
    lines.append("   " + " ".join("abcdef"))
    return "\n".join(lines)


def play_interactive():
    if not sys.stdin.isatty():
        print("交互模式需要终端运行。可用 --auto 观看 AI 对战。")
        sys.exit(2)
    rng = random.Random()
    game = new_game(rng)
    human = 0
    print("你是红方（底线两行），走法如：b2 b3；q 退出。")
    player = 0
    while game.winner is None:
        print(render(game, human))
        if player == human:
            try:
                raw = input("你走: ").strip()
            except EOFError:
                break
            if raw.lower() == "q":
                break
            try:
                a, b = raw.split()
                report = game.apply_move((parse_sq(a), parse_sq(b)), player)
                print(describe_report(game, report, player))
            except (ValueError, IllegalMove) as e:
                print(f"非法走法：{e}")
                continue
        else:
            move = ai_choose(game, player, rng)
            if move is None:
                game.winner = human
                break
            report = game.apply_move(move, player)
            print("蓝方：", describe_report(game, report, player))
        player = 1 - player
    print(render(game, human))
    announce(game.winner)


def announce(winner):
    if winner == "draw":
        print("和棋（达到回合上限）。")
    else:
        print(f"{PLAYER_NAME[winner]}获胜！")


def main(argv=None):
    ap = argparse.ArgumentParser(description="stratego-lite：简化版陆军棋")
    ap.add_argument("--auto", action="store_true", help="AI 对战演示")
    ap.add_argument("--games", type=int, default=10, help="自动对局数")
    ap.add_argument("--seed", type=int, default=42, help="随机种子")
    ap.add_argument("--verbose", action="store_true", help="打印每步走法")
    args = ap.parse_args(argv)
    if args.auto:
        wins = {0: 0, 1: 0, "draw": 0}
        for i in range(args.games):
            game = play_game(args.seed + i, verbose=args.verbose)
            wins[game.winner] += 1
            w = "和棋" if game.winner == "draw" else f"{PLAYER_NAME[game.winner]}胜"
            print(f"第 {i + 1}/{args.games} 局：{w}（{game.half_moves} 半回合）")
        print(f"总计：红方胜 {wins[0]}，蓝方胜 {wins[1]}，和棋 {wins['draw']}")
    else:
        play_interactive()


if __name__ == "__main__":
    main()
