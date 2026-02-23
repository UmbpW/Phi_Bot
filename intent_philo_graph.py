"""Intent: user asks about philosopher influence graph / connections / who influenced whom."""
import re
from typing import List

# Common Russian philosopher names -> English (for DB lookup)
RU_TO_EN_PHILO = {
    "кант": "kant",
    "юм": "hume",
    "аристотель": "aristotle",
    "платон": "plato",
    "сократ": "socrates",
    "декарт": "descartes",
    "ницше": "nietzsche",
    "гегель": "hegel",
    "спиноза": "spinoza",
    "локк": "locke",
    "лейбниц": "leibniz",
    "шопенгауэр": "schopenhauer",
    "киркегор": "kierkegaard",
    "кьеркегор": "kierkegaard",
    "тома": "aquinas",
    "фома аквинский": "thomas aquinas",
}

PHILO_GRAPH_MARKERS = [
    "кто на кого", "кто повлиял", "кто влиял", "влияние", "связи философов",
    "связи:", "покажи связи", "карта философов", "родословная идей",
    "школы философии", "философы и связи", "какой школе", "школа философии",
    "кто критиковал", "критиковал", "кто спорил", "против кого",
    "influence graph", "philosophy graph", "сеть философов", "граф философов",
    "граф влияний",
]


def is_philo_graph_intent(text: str) -> bool:
    t = (text or "").lower()
    return any(m in t for m in PHILO_GRAPH_MARKERS)


def extract_names_naive(text: str) -> List[str]:
    """Optional: naive extraction of capitalized names (e.g. 'Кант и Юм')."""
    t = text or ""
    m = re.findall(r"([A-ZА-ЯЁ][a-zа-яё]+(?:\s+[A-ZА-ЯЁ][a-zа-яё]+){0,2})", t)
    return [x.strip() for x in m][:5]
