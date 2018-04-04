import curses
from curses.textpad import rectangle, Textbox


class ConfigText:
    title = "NuCypher KMS Configurator"
    welcome = "Welcome to the NuCypher KMS Config Tool"
    description = "Use this tool to manage keypairs node operation."
    loading = "loading..."
    keygen_success = "Keys generated and written to keyfile!"


def main(screen):

    height, width = 40, 1
    editwin = curses.newwin(width, height, 2, 1)
    textarea = rectangle(screen, 1, 0, 1+width+1, 1+height+1)  # 1s for padding

    screen.addstr(1, 1, ConfigText.welcome)
    screen.refresh()

    screen.addstr(1, 1, ConfigText.title, curses.A_BOLD)
    screen.refresh()

    box = Textbox(editwin)
    box.edit()    # Let the user edit until Ctrl-G is struck.
    message = box.gather()        # Get resulting contents


if __name__ == "__main__":
    curses.wrapper(main)
    curses.beep()
