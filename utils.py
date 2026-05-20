DAYS_FR = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
MONTHS_FR = [
    "", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"
]


def format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m"


def format_date_fr(dt) -> str:
    return f"{DAYS_FR[dt.weekday()]} {dt.day} {MONTHS_FR[dt.month]} {dt.year}"
