import time
import mesa
from mesa.visualization import SolaraViz, make_space_component

NUM_AGENTS = 5
GRID_SIZE = 10
SEED = 42
EMERGENCY_TIME = 10

class MonitorAgent:
    def __init__(self, model, emergency_time_seconds):
        self.model = model
        self.emergency_time = emergency_time_seconds
        self.emergency_triggered = False

    def step(self):
        elapsed = time.time() - self.model.start_time

        if not self.emergency_triggered and elapsed >= self.emergency_time:
            self.emergency_triggered = True
            self.model.emergency = True

            # notify all evac agents after 10 seconds
            for agent in self.model.agents:
                agent.emergency_triggered = True

class ExitAgent(mesa.Agent):
    def __init__(self, model):
        super().__init__(model)

class EvacAgent(mesa.Agent):
    def __init__(self, model):
        super().__init__(model)
        self.emergency_triggered = False

    def step(self):
        neighbors = self.model.grid.get_neighborhood(
            self.pos,
            moore=False,
            include_center=False,
            radius=1,
        )
        new_pos = self.random.choice(neighbors)
        self.model.grid.move_agent(self, new_pos)


class GridModel(mesa.Model):
    def __init__(self, grid_size=GRID_SIZE, seed=SEED, emergency_time=EMERGENCY_TIME):
        super().__init__(seed=seed)

        self.grid = mesa.space.MultiGrid(grid_size, grid_size, torus=False)
        self.emergency = False
        self.start_time = time.time()

        self.monitor = MonitorAgent(self, emergency_time)

        # Create evac agents
        for _ in range(NUM_AGENTS):
            empty_cells = [
                (x, y)
                for (cell_content, (x, y)) in self.grid.coord_iter()
                if len(cell_content) == 0
            ]
            init_pos = self.random.choice(empty_cells)

            agent = EvacAgent(self)
            self.grid.place_agent(agent, init_pos)

            self.exits = []

            exit_positions = [(0, 0), (grid_size - 1, grid_size - 1)]
            for pos in exit_positions:
                exit_agent = ExitAgent(self)
                self.grid.place_agent(exit_agent, pos)
                self.exits.append(exit_agent)


    def step(self):
        # Monitor checks if 10 seconds passed to give the alarm
        self.monitor.step()

        for agent in self.agents:
            agent.step()


def agent_portrayal(agent):
    if isinstance(agent, ExitAgent):
        return {
            "color": "green",
            "size": 140,
            "marker": "s",
        }
    if isinstance(agent, EvacAgent):
        return {
            "color": "red" if agent.emergency_triggered else "blue",
            "size": 100,
            "marker": "o",
        }

    return {}

if __name__ == "__main__":

    model_params = {
        "grid_size": {
            "type": "SliderInt",
            "value": GRID_SIZE,
            "label": "Grid Size",
            "min": 4,
            "max": 16,
            "step": 1,
        },
    }

    model = GridModel()

    grid_component = make_space_component(agent_portrayal=agent_portrayal)

    page = SolaraViz(
        model=model,
        components=[grid_component],
        model_params=model_params,
        name="Evacuation – 10s Emergency (No Scheduler)",
    )

    page
