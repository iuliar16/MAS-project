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
        self.direction = None
        self.evacuated = False

    def get_visible_exits(self, radius=5):
        visible_exits = []
        x, y = self.pos
        for exit_agent in self.model.exits:
            ex, ey = exit_agent.pos
            if abs(ex - x) <= radius and abs(ey - y) <= radius:
                visible_exits.append(exit_agent)
        return visible_exits

    def closest_exit(self, exits):
        x, y = self.pos
        closest = min(exits, key=lambda e: abs(e.pos[0] - x) + abs(e.pos[1] - y))
        return closest

    def move_towards(self, target_pos):
        x, y = self.pos
        tx, ty = target_pos
        dx = tx - x
        dy = ty - y

        move_options = []
        if dx != 0:
            move_options.append((x + (1 if dx > 0 else -1), y))
        if dy != 0:
            move_options.append((x, y + (1 if dy > 0 else -1)))

        for nx, ny in move_options:
            if not self.model.grid.out_of_bounds((nx, ny)) and len(
                    self.model.grid.get_cell_list_contents((nx, ny))) == 0:
                self.model.grid.move_agent(self, (nx, ny))
                return True

        return False

    def pick_random_direction(self):
        directions = [(0, 1), (0, -1), (1, 0), (-1, 0)]
        self.direction = self.random.choice(directions)

    def best_free_step_towards_exit(self, exit_agent):
        x, y = self.pos
        tx, ty = exit_agent.pos

        # Get all orthogonal neighbors
        neighbors = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]

        # Keep only neighbors that are inside the grid and free
        free_neighbors = [
            n for n in neighbors
            if not self.model.grid.out_of_bounds(n)
               and len(self.model.grid.get_cell_list_contents(n)) == 0
        ]

        if not free_neighbors:
            return None  # all neighbors blocked

        # Pick the neighbor that minimizes Manhattan distance to exit
        best_cell = min(free_neighbors, key=lambda n: abs(n[0] - tx) + abs(n[1] - ty))
        return best_cell

    def check_exit(self):
        for exit_agent in self.model.exits:
            if self.pos == exit_agent.pos:
                self.model.kill_agents.append(self)
                return True
        return False

    def step(self):
        # before emergency = random walking
        if not self.emergency_triggered:
            neighbors = self.model.grid.get_neighborhood(
                self.pos,
                moore=False,
                include_center=False,
                radius=1,
            )
            new_pos = self.random.choice(neighbors)
            if len(self.model.grid.get_cell_list_contents(new_pos)) == 0:
                self.model.grid.move_agent(self, new_pos)
                self.check_exit()
            return

        # after emergency = constant direction walking
        if self.direction is None:
            self.pick_random_direction()

        visible_exits = self.get_visible_exits(radius=5)
        if visible_exits:
            exit_agent = self.closest_exit(visible_exits)
            moved = self.move_towards(exit_agent.pos)

            # If direct path is blocked, try the best free step towards exit
            if not moved:
                target_cell = self.best_free_step_towards_exit(exit_agent)
                if target_cell:
                    self.model.grid.move_agent(self, target_cell)
                    self.check_exit()
            return

        # If the agent hits a wall, then he should pick a new direction
        # Find a valid move direction
        attempts = 0
        while True:
            x, y = self.pos
            dx, dy = self.direction or (0, 0)
            target = (x + dx, y + dy)

            # Check for visible exits first
            visible_exits = self.get_visible_exits(radius=5)
            if visible_exits:
                exit_agent = self.closest_exit(visible_exits)
                target = self.next_step_towards(exit_agent.pos)  # minimal helper to get next step
                if target and len(self.model.grid.get_cell_list_contents(target)) == 0:
                    break

            # valid cell
            if not self.model.grid.out_of_bounds(target) and len(self.model.grid.get_cell_list_contents(target)) == 0:
                break

            # Pick a new direction and retry
            self.pick_random_direction()
            attempts += 1

            if attempts > 10:
                # fallback to random walk if stuck
                neighbors = self.model.grid.get_neighborhood(
                    self.pos,
                    moore=False,
                    include_center=False,
                    radius=1,
                )
                # choose a free neighbor if any
                free_neighbors = [n for n in neighbors if len(self.model.grid.get_cell_list_contents(n)) == 0]
                if free_neighbors:
                    target = self.random.choice(free_neighbors)
                else:
                    target = self.pos  # stay in place
                break

        # Move to the new position
        self.model.grid.move_agent(self, target)
        self.check_exit()

class GridModel(mesa.Model):
    def __init__(self, grid_size=GRID_SIZE, seed=SEED, emergency_time=EMERGENCY_TIME):
        super().__init__(seed=seed)

        self.grid = mesa.space.MultiGrid(grid_size, grid_size, torus=False)
        self.emergency = False
        self.start_time = time.time()
        self.kill_agents = []

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

        # Asta nu merge. Idk why -_-
        for agent in self.kill_agents:
            self.grid.remove_agent(agent)
        self.kill_agents.clear()


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
