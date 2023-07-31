import difflib

from colorama import Fore


def print_diff(original: str, modified: str):
    diff = difflib.ndiff(original.splitlines(), modified.splitlines())
    for line in diff:
        if line.startswith("-"):
            print(Fore.RED + line + Fore.RESET)
        elif line.startswith("+"):
            print(Fore.GREEN + line + Fore.RESET)


def print_info(info: str):
    print(Fore.WHITE + info + Fore.RESET)


def print_section_header(header: str):
    print(Fore.MAGENTA + f"\n======= {header} =======\n" + Fore.RESET)
