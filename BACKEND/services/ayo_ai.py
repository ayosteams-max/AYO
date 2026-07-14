from BACKEND.models.driver import Driver


def calculate_ayo_score(
    driver: Driver,
    distance_km: float,
) -> float:
    """
    First version of the AYO AI score.

    Higher score = better driver.
    """

    score = 100.0

    # Distance (closer is better)
    score -= distance_km * 2

    # Customer rating
    score += driver.rating * 2

    # Verified drivers bonus
    if driver.verified:
        score += 5

    # Premium bonus
    if driver.premium_eligible:
        score += 3

    # Airport bonus
    if driver.airport_eligible:
        score += 3

    return round(score, 2)
