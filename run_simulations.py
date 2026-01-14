import pandas as pd

from main import GRID_SIZE, EMERGENCY_TIME, GridModel
# to be able to run this file, we need to set EMERGENCY_TIME to 0 in main

placements = {
    "Opposite corners": [(0, 0), (GRID_SIZE - 1, GRID_SIZE - 1)],
    "Middle left/right": [(0, GRID_SIZE // 2), (GRID_SIZE - 1, GRID_SIZE // 2)],
    "Adjacent corners bottom": [(0, 0), (GRID_SIZE - 1, 0)],
    "Single center exit": [(GRID_SIZE // 2, GRID_SIZE // 2)],
}

def run_one_simulation(exit_positions, seed, grid_size=GRID_SIZE, emergency_time=EMERGENCY_TIME, max_steps=10_000):
    model = GridModel(
        grid_size=grid_size,
        seed=seed,
        emergency_time=emergency_time,
        exit_positions=exit_positions,
    )

    steps = 0
    while model.running and steps < max_steps:
        model.step()
        steps += 1

    evac_steps = model.get_evacuation_steps()
    return evac_steps


def evaluate_exit_placements(runs=30, base_seed=1000):
    rows = []

    for placement_name, exit_positions in placements.items():
        results = []

        for run_index in range(runs):
            seed = base_seed + run_index  # different seed each run
            evac_steps = run_one_simulation(exit_positions=exit_positions, seed=seed)

            # if something went wrong record None
            results.append(evac_steps)

        valid = [r for r in results if r is not None]

        rows.append({
            "placement": placement_name,
            "exits": str(exit_positions),
            "runs": runs,
            "finished_runs": len(valid),
            "mean_steps": sum(valid) / len(valid) if valid else None,
            "min_steps": min(valid) if valid else None,
            "max_steps": max(valid) if valid else None,
            "std_steps": (pd.Series(valid).std(ddof=1) if len(valid) > 1 else 0.0) if valid else None,
        })

    df = pd.DataFrame(rows).sort_values(by="mean_steps", ascending=True)
    return df

if __name__ == "__main__":
    df = evaluate_exit_placements(runs_per_placement=50, base_seed=2000)
    print(df.to_string(index=False))
