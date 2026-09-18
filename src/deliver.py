"""Post the announcements the pipeline queued, after the run's files are
pushed.

`src/draft_requests.py` drafts a resume, writes the files and queues the
issue comment; the workflow pushes the commit and then runs this. Keeping
the two apart means a failed push can no longer close a draft request that
links to files nobody can open.

Run: python -m src.deliver
"""
import logging
import sys

from . import draft_requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def main() -> int:
    n = draft_requests.deliver_queued()
    if n:
        logging.getLogger(__name__).info("Delivered %d queued announcement(s)", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
