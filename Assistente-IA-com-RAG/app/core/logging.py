import logging
import sys


def setup_logging(debug: bool = False) -> None:
    """Configura o sistema de log da aplicação com formatação estruturada."""
    log_level = logging.DEBUG if debug else logging.INFO
    log_format = "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s"

    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    """Retorna um logger configurado para o módulo informado."""
    return logging.getLogger(name)
