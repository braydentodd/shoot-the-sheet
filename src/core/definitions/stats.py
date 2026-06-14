"""
Shoot the Sheet - Stat Rate Definitions

Cross-cutting rate definitions used by ETL promotion and Publish scaling.

The ``STAT_RATES`` dict defines the rate modes a league can compute.
Each league declares which rates to use in its ``stat_rates`` list
(see :data:`src.core.definitions.leagues.LEAGUES`).

Individual per-dataset domain configuration (tracking, hustle, etc.)
lives in each dataset's ``source_mapping.domain`` inside
:data:`src.etl.definitions.datasets.DATASETS`.
"""

from typing import Dict

STAT_RATES: Dict[str, dict] = {
    "per_poss": {"short_label": "Poss", "rate": 100},
    "per_min": {"short_label": "Min", "rate": 40},
}
