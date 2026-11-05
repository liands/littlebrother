import os
import random
import sys
from datetime import datetime

from colorama import Fore

import settings
from txt.header import lb_header
from txt.text import text

def checkVersion():
    if sys.version_info < (3, 10):
        raise RuntimeError("É necessário Python 3.10 ou superior.")

def clear():
    if sys.stdout.isatty():
        os.system("cls" if os.name == "nt" else "clear")

def times():
    return datetime.now().strftime("%H:%M:%S")


def color(value, foreground):
    if sys.stdout.isatty() and "NO_COLOR" not in os.environ:
        return foreground + str(value) + Fore.RESET
    return str(value)


def prompt(section="~"):
    return "\n LittleBrother(" + color(section, Fore.BLUE) + ")$ "


def menu():
    # Only read the local database; the original panel never needs a network call.
    from core.Profiler import Profiler
    database = Profiler(root=settings.pathDatabase) if settings.pathDatabase else Profiler()
    if settings.pathDatabase:
        database.loadDatabase(settings.pathDatabase)
    now = datetime.now()
    panel = r"""
                         __..--.._
  .....              .--~  .....  `.         Time:      [ %s | %s ]
.":    "`-..  .    .' ..-'"    :". `         Author:    [ Lulz3xploit ] ‖ Revised: [ Lica ]
` `._ ` _.'`"(     `-"'`._ ' _.' '           Version:   [ %s ]
     ~~~      `.          ~~~                País:      [ %s | %s ]
              .'                             Database:  [ %s | %s Ko ]
             /
            (                             %s
             ^---'
""" % (color(now.date(), Fore.YELLOW), color(now.strftime("%H:%M:%S"), Fore.YELLOW),
       color(settings.version, Fore.YELLOW), color(settings.monpays, Fore.CYAN),
       settings.codemonpays, color(database.count, Fore.GREEN),
       color("%.2f" % database.size, Fore.RED), random.choice(text))
    print(lb_header())
    print(panel)


def show_screen(options):
    clear()
    menu()
    print(options)
