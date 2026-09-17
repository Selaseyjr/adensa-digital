import logging

from app.bootstrap import initialize_adensa
from app.main import main


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    initialize_adensa()
    main()