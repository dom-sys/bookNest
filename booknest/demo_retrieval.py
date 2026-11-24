"""Run from the repository folder: python3 -m booknest.demo_retrieval"""

import argparse
from pathlib import Path

from .ai import Assistant


def main():
    default_book = Path(__file__).resolve().parent.parent / "data" / "sample_book.json"
    parser = argparse.ArgumentParser(description="Ask questions about completed book chapters.")
    parser.add_argument("book_file", nargs="?", default=default_book,
                        help="Path to a book JSON file; defaults to the sample story.")
    arguments = parser.parse_args()
    try:
        assistant = Assistant(arguments.book_file)
    except ValueError as error:
        print(f"Could not load book: {error}")
        return 1

    print(f"Ask-the-Book: {assistant.title}")
    print(f"There are {assistant.chapter_count} chapters. Enter 0 if you haven't started.")
    print("Type quit at either prompt to exit.\n")

    while True:
        chapter_input = input("Last chapter completed: ").strip()
        if chapter_input.lower() == "quit":
            break

        try:
            completed_chapter = int(chapter_input)
        except ValueError:
            print("Please enter a whole chapter number.\n")
            continue

        if not 0 <= completed_chapter <= assistant.chapter_count:
            print(f"Choose a chapter from 0 to {assistant.chapter_count}.\n")
            continue

        question = input("Your question: ").strip()
        if question.lower() == "quit":
            break

        try:
            answer = assistant.ask_book(completed_chapter, question)
        except ValueError as error:
            print(f"{error}\n")
            continue

        print(f"\n{answer}\n")

    print("Goodbye!")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EOFError, KeyboardInterrupt):
        # Closing input or pressing Ctrl+C also ends the demo cleanly.
        print("\nGoodbye!")
