import os

import nba_on_court as noc
import pandas as pd

noc.load_nba_data(
    seasons=2021,
    data=("pbpstats",),
    seasontype="po",
    league="nba",
    untar=True,
)

pbpstats = pd.read_csv("pbpstats_po_2021.csv", dtype={"GAMEID": str})

target = str(int("0042100151"))

game = pbpstats[pbpstats["GAMEID"] == target]

print(sorted(os.listdir(".")))
print([f for f in os.listdir(".") if "2021" in f and f.endswith(".csv")])

print(game.shape)
print(game.head(20).to_string())

charge_rows = game[
    game["DESCRIPTION"].astype(str).str.contains("charge", case=False, na=False)
]

print(charge_rows.to_string())

print(game["URL"].dropna().head(20).tolist())
