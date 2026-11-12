#oftsline_calculator.py
#run it with python softline_calculator.py. 
#It uses only Python’s standard library and Tkinter.

import ast
import math
import re
import tkinter as tk
from dataclasses import dataclass
from tkinter import font as tkfont
from typing import Dict, List, Optional, Tuple


# ── Palette ────────────────────────────────────────────────────────────────

WINDOW_YELLOW = "#F3E8B7"
PANEL_YELLOW = "#FBF4DC"
PANEL_SHADOW = "#E3D7A4"
BUTTON_SHADOW = "#E4D9B7"

INK = "#171717"
MUTED = "#827953"
RULE = "#E8DEBE"
WHITE = "#FFFFFF"
ERROR = "#9A4938"

BUTTON_BLACK = "#101010"
BUTTON_HOVER = "#252525"
BUTTON_CLICK = "#3A3A3A"


# ── Safe arithmetic ────────────────────────────────────────────────────────

NUMBER_SUFFIX = re.compile(
    r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$"
)
ALLOWED_EXPRESSION_CHARACTERS = set("0123456789.+-*/%eE()")


def safe_evaluate(expression: str) -> float:
    """Evaluate basic arithmetic without using Python's eval()."""
    if not expression or len(expression) > 120:
        raise ValueError("Expression is empty or too long.")

    if any(char not in ALLOWED_EXPRESSION_CHARACTERS for char in expression):
        raise ValueError("Unsupported character.")

    # Here % means “percent”: 50% becomes 50/100.
    normalized = expression.replace("%", "/100")
    tree = ast.parse(normalized, mode="eval")

    if sum(1 for _ in ast.walk(tree)) > 256:
        raise ValueError("Expression is too complex.")

    def checked(value: float) -> float:
        if not math.isfinite(value):
            raise OverflowError("Result is outside the display range.")
        return value

    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)

        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return checked(float(node.value))

        if isinstance(node, ast.UnaryOp):
            operand = visit(node.operand)
            if isinstance(node.op, ast.UAdd):
                return checked(operand)
            if isinstance(node.op, ast.USub):
                return checked(-operand)
            raise ValueError("Unsupported unary operation.")

        if isinstance(node, ast.BinOp):
            left = visit(node.left)
            right = visit(node.right)

            if isinstance(node.op, ast.Add):
                return checked(left + right)
            if isinstance(node.op, ast.Sub):
                return checked(left - right)
            if isinstance(node.op, ast.Mult):
                return checked(left * right)
            if isinstance(node.op, ast.Div):
                if right == 0:
                    raise ZeroDivisionError
                return checked(left / right)

            raise ValueError("Unsupported operation.")

        raise ValueError("Invalid expression.")

    return visit(tree)


def format_number(value: float) -> str:
    """Format answers neatly, avoiding trailing .0 and noisy float digits."""
    if value == 0:
        return "0"

    if value.is_integer() and abs(value) < 1e15:
        return str(int(value))

    return format(value, ".12g")


# ── Drawing helpers ────────────────────────────────────────────────────────

def rounded_rectangle(canvas, x1, y1, x2, y2, radius, **options):
    """Draw a smoothly rounded rectangle on a Tkinter Canvas."""
    radius = max(0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))

    points = [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1, x2, y1 + radius,
        x2, y2 - radius,
        x2, y2, x2 - radius, y2,
        x1 + radius, y2,
        x1, y2, x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]

    return canvas.create_polygon(
        *points,
        smooth=True,
        splinesteps=24,
        **options
    )


def blend_color(first: str, second: str, amount: float) -> str:
    """Blend two #RRGGBB colors for subtle button animations."""
    amount = max(0.0, min(1.0, amount))
    first_rgb = tuple(int(first[i:i + 2], 16) for i in (1, 3, 5))
    second_rgb = tuple(int(second[i:i + 2], 16) for i in (1, 3, 5))

    blended = tuple(
        round(a + (b - a) * amount)
        for a, b in zip(first_rgb, second_rgb)
    )
    return "#{:02x}{:02x}{:02x}".format(*blended)


# ── Button definitions ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class ButtonSpec:
    name: str
    label: str
    action: str
    compact: bool = False


BUTTON_ROWS = (
    (
        ButtonSpec("clear", "AC", "clear", True),
        ButtonSpec("delete", "DEL", "delete", True),
        ButtonSpec("percent", "%", "%"),
        ButtonSpec("divide", "÷", "/"),
    ),
    (
        ButtonSpec("7", "7", "7"),
        ButtonSpec("8", "8", "8"),
        ButtonSpec("9", "9", "9"),
        ButtonSpec("multiply", "×", "*"),
    ),
    (
        ButtonSpec("4", "4", "4"),
        ButtonSpec("5", "5", "5"),
        ButtonSpec("6", "6", "6"),
        ButtonSpec("subtract", "−", "-"),
    ),
    (
        ButtonSpec("1", "1", "1"),
        ButtonSpec("2", "2", "2"),
        ButtonSpec("3", "3", "3"),
        ButtonSpec("add", "+", "+"),
    ),
    (
        ButtonSpec("sign", "±", "sign"),
        ButtonSpec("0", "0", "0"),
        ButtonSpec("decimal", ".", "."),
        ButtonSpec("equals", "=", "="),
    ),
)


# ── Calculator application ─────────────────────────────────────────────────

class CalculatorApp:
    MAX_EXPRESSION_LENGTH = 120
    OPERATORS = "+-*/"

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Softline Calculator")
        self.root.geometry("440x730")
        self.root.minsize(360, 600)
        self.root.configure(bg=WINDOW_YELLOW)

        self.canvas = tk.Canvas(
            root,
            bg=WINDOW_YELLOW,
            highlightthickness=0,
            borderwidth=0,
            takefocus=True,
        )
        self.canvas.pack(fill="both", expand=True)

        self.expression = ""
        self.last_result: Optional[float] = None
        self.just_evaluated = False
        self.feedback: Optional[str] = None

        self.button_specs = {
            button.name: button
            for row in BUTTON_ROWS
            for button in row
        }
        self.button_bounds: Dict[str, Tuple[float, float, float, float]] = {}

        self.hovered_button: Optional[str] = None
        self.pressed_button: Optional[str] = None
        self.hover_amount = {name: 0.0 for name in self.button_specs}
        self.flash_amount = {name: 0.0 for name in self.button_specs}
        self.animation_job = None
        self.last_canvas_size = (0, 0)

        default_font = tkfont.nametofont("TkDefaultFont", root=self.root)
        self.font_family = default_font.actual("family")
        self.font_cache: Dict[Tuple[int, str], tkfont.Font] = {}

        self.canvas.bind("<Configure>", self._on_configure)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.root.bind_all("<KeyPress>", self._on_key)

    # ── Fonts and layout ───────────────────────────────────────────────

    def _font(self, size: int, weight: str = "normal") -> tkfont.Font:
        key = (int(size), weight)
        if key not in self.font_cache:
            self.font_cache[key] = tkfont.Font(
                root=self.root,
                family=self.font_family,
                size=int(size),
                weight=weight,
            )
        return self.font_cache[key]

    def _fit_font(
        self,
        text: str,
        max_width: float,
        preferred_size: int,
        minimum_size: int,
        weight: str = "normal",
    ) -> tkfont.Font:
        size = preferred_size
        while size > minimum_size and self._font(size, weight).measure(text) > max_width:
            size -= 1
        return self._font(size, weight)

    def _on_configure(self, event):
        size = (event.width, event.height)
        if size != self.last_canvas_size:
            self.last_canvas_size = size
            self._draw_scene(event.width, event.height)

    def _redraw(self):
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        if width >= 100 and height >= 100:
            self.last_canvas_size = (width, height)
            self._draw_scene(width, height)

    def _format_expression(self, expression: str) -> str:
        """Show calculator operators using typographic symbols."""
        display = []

        for index, char in enumerate(expression):
            symbol = {"*": "×", "/": "÷", "-": "−"}.get(char, char)

            # Keep the sign in scientific notation attached to its exponent.
            exponent_sign = (
                char in "+-"
                and index > 0
                and expression[index - 1] in "eE"
            )

            if char in "+-*/" and not exponent_sign:
                display.append(" " + symbol + " ")
            else:
                display.append(symbol)

        return " ".join("".join(display).split())

    def _split_long_word(self, word: str, font, max_width: float) -> List[str]:
        chunks = []
        current = ""

        for char in word:
            candidate = current + char
            if current and font.measure(candidate) > max_width:
                chunks.append(current)
                current = char
            else:
                current = candidate

        if current:
            chunks.append(current)

        return chunks or [""]

    def _wrap_text(self, text: str, font, max_width: float) -> List[str]:
        """Wrap expression text cleanly, including unusually long numbers."""
        lines = []
        current = ""

        for word in text.split():
            if font.measure(word) > max_width:
                if current:
                    lines.append(current)
                    current = ""

                chunks = self._split_long_word(word, font, max_width)
                lines.extend(chunks[:-1])
                current = chunks[-1]
                continue

            candidate = (current + " " + word).strip()
            if not current or font.measure(candidate) <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word

        if current:
            lines.append(current)

        return lines or [""]

    def _draw_scene(self, width: int, height: int):
        if width < 100 or height < 100:
            return

        self.canvas.delete("all")
        self.button_bounds = {}

        card_width = min(width - 24, 520)
        card_x = (width - card_width) / 2
        card_y = 12
        card_right = card_x + card_width
        card_bottom = height - 12

        rounded_rectangle(
            self.canvas,
            card_x,
            card_y + 5,
            card_right,
            card_bottom + 5,
            26,
            fill=PANEL_SHADOW,
            outline=PANEL_SHADOW,
        )
        rounded_rectangle(
            self.canvas,
            card_x,
            card_y,
            card_right,
            card_bottom,
            26,
            fill=PANEL_YELLOW,
            outline=PANEL_YELLOW,
        )

        padding_x = max(22, min(34, int(card_width * 0.064)))
        content_left = card_x + padding_x
        content_right = card_right - padding_x
        content_width = content_right - content_left

        # Header and compact calculator mark.
        header_y = card_y + 25
        rounded_rectangle(
            self.canvas,
            content_left,
            header_y,
            content_left + 36,
            header_y + 36,
            11,
            fill=INK,
            outline=INK,
        )
        self.canvas.create_text(
            content_left + 18,
            header_y + 18,
            text="+",
            font=self._font(22, "bold"),
            fill=WHITE,
            anchor="center",
        )
        self.canvas.create_text(
            content_left + 49,
            header_y + 3,
            text="CALCULATOR",
            font=self._font(12, "bold"),
            fill=INK,
            anchor="nw",
        )
        self.canvas.create_text(
            content_left + 49,
            header_y + 21,
            text="JUST THE ESSENTIALS",
            font=self._font(8, "normal"),
            fill=MUTED,
            anchor="nw",
        )
        self.canvas.create_text(
            content_right,
            header_y + 18,
            text="01",
            font=self._font(10, "bold"),
            fill=MUTED,
            anchor="e",
        )

        self.canvas.create_line(
            content_left,
            card_y + 76,
            content_right,
            card_y + 76,
            fill=RULE,
            width=1,
        )

        # Expression display.
        expression_label_y = card_y + 84
        expression_top = card_y + 100

        self.canvas.create_text(
            content_left,
            expression_label_y,
            text="EXPRESSION",
            font=self._font(9, "bold"),
            fill=MUTED,
            anchor="nw",
        )

        if self.expression:
            expression_text = self._format_expression(self.expression)
            expression_color = "#514A35"
        else:
            expression_text = "Ready when you are"
            expression_color = MUTED

        expression_font = self._font(15, "normal")
        expression_lines = self._wrap_text(
            expression_text,
            expression_font,
            content_width,
        )
        self.canvas.create_text(
            content_right,
            expression_top,
            text="\n".join(expression_lines),
            font=expression_font,
            fill=expression_color,
            anchor="ne",
            justify="right",
        )

        line_height = expression_font.metrics("linespace") + 2
        expression_height = line_height * len(expression_lines)
        result_label_y = expression_top + expression_height + 7
        result_center_y = result_label_y + 32

        self.canvas.create_text(
            content_left,
            result_label_y,
            text="RESULT",
            font=self._font(9, "bold"),
            fill=MUTED,
            anchor="nw",
        )

        result_text, result_color, preferred_size, minimum_size = self._result_state()
        result_font = self._fit_font(
            result_text,
            content_width,
            preferred_size,
            minimum_size,
            "bold",
        )
        self.canvas.create_text(
            content_right,
            result_center_y,
            text=result_text,
            font=result_font,
            fill=result_color,
            anchor="e",
            justify="right",
        )

        # Responsive five-row keypad.
        rows = len(BUTTON_ROWS)
        gap = max(8, min(12, int(card_width * 0.025)))
        bottom_padding = max(22, int(height * 0.04))
        minimum_row_height = 52

        desired_top = max(
            card_y + 208,
            int(height * 0.30),
            int(result_center_y + 46),
        )
        maximum_top = (
            height
            - bottom_padding
            - rows * minimum_row_height
            - (rows - 1) * gap
        )
        button_top = min(desired_top, maximum_top)

        row_height = (
            height - button_top - bottom_padding - (rows - 1) * gap
        ) / rows
        column_width = (content_width - 3 * gap) / 4

        for row_index, row in enumerate(BUTTON_ROWS):
            y1 = button_top + row_index * (row_height + gap)
            y2 = y1 + row_height

            for column_index, button in enumerate(row):
                x1 = content_left + column_index * (column_width + gap)
                x2 = x1 + column_width
                self.button_bounds[button.name] = (x1, y1, x2, y2)

        self._draw_buttons()

    def _result_state(self):
        if self.feedback:
            return self.feedback, ERROR, 21, 14

        if self.just_evaluated and self.last_result is not None:
            return format_number(self.last_result), INK, 44, 18

        if not self.expression:
            return "0", INK, 44, 18

        try:
            return format_number(safe_evaluate(self.expression)), INK, 44, 18
        except ZeroDivisionError:
            return "Cannot divide by zero", ERROR, 21, 14
        except OverflowError:
            return "Out of range", ERROR, 22, 14
        except Exception:
            return "—", MUTED, 44, 18

    # ── Button drawing and animation ───────────────────────────────────

    def _draw_buttons(self):
        self.canvas.delete("calculator_buttons")

        for row in BUTTON_ROWS:
            for button in row:
                if button.name not in self.button_bounds:
                    continue

                x1, y1, x2, y2 = self.button_bounds[button.name]
                pressed = self.pressed_button == button.name
                vertical_shift = 2 if pressed else 0

                rounded_rectangle(
                    self.canvas,
                    x1,
                    y1 + 4,
                    x2,
                    y2 + 3,
                    min(17, min(x2 - x1, y2 - y1) * 0.24),
                    fill=BUTTON_SHADOW,
                    outline=BUTTON_SHADOW,
                    tags=("calculator_buttons",),
                )

                color = blend_color(
                    BUTTON_BLACK,
                    BUTTON_HOVER,
                    self.hover_amount[button.name],
                )
                color = blend_color(
                    color,
                    BUTTON_CLICK,
                    self.flash_amount[button.name],
                )
                if pressed:
                    color = BUTTON_CLICK

                radius = min(17, min(x2 - x1, y2 - y1) * 0.24)
                rounded_rectangle(
                    self.canvas,
                    x1,
                    y1 + vertical_shift,
                    x2,
                    y2 - 4 + vertical_shift,
                    radius,
                    fill=color,
                    outline=color,
                    tags=("calculator_buttons",),
                )

                if button.compact:
                    font_size = max(12, min(16, int(min(x2 - x1, y2 - y1) * 0.22)))
                else:
                    font_size = max(21, min(34, int(min(x2 - x1, y2 - y1) * 0.43)))

                self.canvas.create_text(
                    (x1 + x2) / 2,
                    (y1 + y2 - 4) / 2 + vertical_shift,
                    text=button.label,
                    font=self._font(font_size, "bold"),
                    fill=WHITE,
                    anchor="center",
                    tags=("calculator_buttons",),
                )

    def _button_at(self, x: float, y: float) -> Optional[str]:
        for name, (x1, y1, x2, y2) in self.button_bounds.items():
            if x1 <= x <= x2 and y1 <= y <= y2:
                return name
        return None

    def _on_motion(self, event):
        new_hovered = self._button_at(event.x, event.y)
        if new_hovered != self.hovered_button:
            self.hovered_button = new_hovered
            self.canvas.configure(cursor="hand2" if new_hovered else "arrow")
            self._start_animation()

    def _on_press(self, event):
        self.canvas.focus_set()
        self.pressed_button = self._button_at(event.x, event.y)
        if self.pressed_button:
            self._draw_buttons()

    def _on_release(self, event):
        pressed = self.pressed_button
        self.pressed_button = None

        if pressed and self._button_at(event.x, event.y) == pressed:
            self.flash_amount[pressed] = 1.0
            self._activate(self.button_specs[pressed].action)
            self._start_animation()
        else:
            self._draw_buttons()

    def _start_animation(self):
        if self.animation_job is None:
            self.animation_job = self.root.after(16, self._animate)

    def _animate(self):
        self.animation_job = None
        still_animating = False

        for name in self.button_specs:
            target = 1.0 if name == self.hovered_button else 0.0
            current = self.hover_amount[name]
            current += (target - current) * 0.42

            if abs(target - current) < 0.025:
                current = target
            else:
                still_animating = True

            self.hover_amount[name] = current

            flash = self.flash_amount[name] * 0.70
            if flash < 0.025:
                flash = 0.0
            else:
                still_animating = True
            self.flash_amount[name] = flash

        self._draw_buttons()

        if still_animating:
            self.animation_job = self.root.after(16, self._animate)

    # ── Calculator input ───────────────────────────────────────────────

    def _set_expression(self, expression: str):
        if len(expression) > self.MAX_EXPRESSION_LENGTH:
            self.feedback = "Expression is too long"
            self._redraw()
            return False

        self.expression = expression
        self.feedback = None
        self._redraw()
        return True

    def _continue_from_result(self):
        if self.just_evaluated:
            if self.last_result is not None:
                self.expression = format_number(self.last_result)
            self.just_evaluated = False

    def _input_digit(self, digit: str):
        if self.just_evaluated:
            self.expression = ""
            self.just_evaluated = False

        expression = self.expression

        # Typing after a completed percentage or group starts multiplication.
        if expression.endswith(("%", ")")):
            expression += "*"

        match = NUMBER_SUFFIX.search(expression)
        if match and match.group() == "0":
            # Prevent invalid literals such as 007.
            expression = expression[:match.start()] + digit
        else:
            expression += digit

        self._set_expression(expression)

    def _input_decimal(self):
        if self.just_evaluated:
            self.expression = ""
            self.just_evaluated = False

        expression = self.expression

        if not expression:
            expression = "0."
        elif expression.endswith(("%", ")")):
            expression += "*0."
        elif expression[-1] in self.OPERATORS:
            expression += "0."
        else:
            match = NUMBER_SUFFIX.search(expression)
            if not match:
                expression += "0."
            else:
                current_number = match.group()
                if "." in current_number or "e" in current_number.lower():
                    return
                expression += "."

        self._set_expression(expression)

    def _input_operator(self, operator: str):
        self._continue_from_result()
        expression = self.expression

        if not expression:
            if operator == "-":
                self._set_expression("-")
            return

        if expression[-1] not in self.OPERATORS:
            self._set_expression(expression + operator)
            return

        if self._ends_with_unary_minus(expression):
            if operator == "-":
                return

            without_unary_minus = expression[:-1]
            if without_unary_minus and without_unary_minus[-1] in self.OPERATORS:
                expression = without_unary_minus[:-1] + operator
            else:
                expression = ""
        elif operator == "-":
            # A second minus starts a negative operand, e.g. 5 - -2.
            expression += "-"
        else:
            expression = expression[:-1] + operator

        self._set_expression(expression)

    def _input_percent(self):
        self._continue_from_result()
        expression = self.expression

        if not expression or expression.endswith("%"):
            return

        if expression.endswith(")") or NUMBER_SUFFIX.search(expression):
            self._set_expression(expression + "%")

    def _input_sign(self):
        self._continue_from_result()
        expression = self.expression

        percent = expression.endswith("%")
        base = expression[:-1] if percent else expression
        match = NUMBER_SUFFIX.search(base)

        if match:
            start, end = match.span()

            # Include a preceding minus only when it is a unary sign.
            if start > 0 and base[start - 1] == "-":
                previous = base[start - 2] if start >= 2 else ""
                if not previous or previous in self.OPERATORS:
                    start -= 1

            number = base[start:end]
            replacement = number[1:] if number.startswith("-") else "-" + number
            updated = base[:start] + replacement

            if percent:
                updated += "%"
            self._set_expression(updated)
            return

        if not expression:
            self._set_expression("-")
        elif self._ends_with_unary_minus(expression):
            self._set_expression(expression[:-1])
        elif expression[-1] in self.OPERATORS:
            self._set_expression(expression + "-")

    def _delete(self):
        self.just_evaluated = False
        self.feedback = None

        if self.expression:
            self._set_expression(self.expression[:-1])
        else:
            self._redraw()

    def _clear(self):
        self.expression = ""
        self.last_result = None
        self.just_evaluated = False
        self.feedback = None
        self._redraw()

    def _equals(self):
        if not self.expression:
            return

        try:
            result = safe_evaluate(self.expression)
        except ZeroDivisionError:
            self.just_evaluated = False
            self.feedback = "Cannot divide by zero"
        except OverflowError:
            self.just_evaluated = False
            self.feedback = "Result out of range"
        except Exception:
            self.just_evaluated = False
            self.feedback = (
                "Complete the expression"
                if self.expression[-1] in self.OPERATORS
                else "Invalid expression"
            )
        else:
            self.last_result = result
            self.just_evaluated = True
            self.feedback = None

        self._redraw()

    @staticmethod
    def _ends_with_unary_minus(expression: str) -> bool:
        return expression.endswith("-") and (
            len(expression) == 1 or expression[-2] in "+-*/"
        )

    def _activate(self, action: str):
        if action == "clear":
            self._clear()
        elif action == "delete":
            self._delete()
        elif action == "sign":
            self._input_sign()
        elif action == "%":
            self._input_percent()
        elif action == ".":
            self._input_decimal()
        elif action == "=":
            self._equals()
        elif action in self.OPERATORS:
            self._input_operator(action)
        elif len(action) == 1 and action in "0123456789":
            self._input_digit(action)

    def _on_key(self, event):
        keysym = event.keysym

        if keysym in ("Return", "KP_Enter", "KP_Equal"):
            self._activate("=")
            return "break"

        if keysym in ("BackSpace",):
            self._activate("delete")
            return "break"

        if keysym in ("Delete", "Escape"):
            self._activate("clear")
            return "break"

        keypad_actions = {
            "KP_Add": "+",
            "KP_Subtract": "-",
            "KP_Multiply": "*",
            "KP_Divide": "/",
            "KP_Decimal": ".",
        }
        if keysym in keypad_actions:
            self._activate(keypad_actions[keysym])
            return "break"

        if keysym.startswith("KP_") and keysym[-1:] in "0123456789":
            self._activate(keysym[-1])
            return "break"

        char = event.char
        if char in "0123456789":
            self._activate(char)
            return "break"

        keyboard_actions = {
            "+": "+",
            "-": "-",
            "−": "-",
            "*": "*",
            "x": "*",
            "X": "*",
            "×": "*",
            "/": "/",
            "÷": "/",
            "%": "%",
            ".": ".",
            "=": "=",
            "±": "sign",
        }
        if char in keyboard_actions:
            self._activate(keyboard_actions[char])
            return "break"

        return None


def main():
    root = tk.Tk()
    CalculatorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()


#Mouse buttons and keyboard input are supported: use `0–9`, `+`, `-`, `*`, `/`, `%`, `.`, `Enter`, and `Backspace`. `Escape` or `Delete` clears the calculator.