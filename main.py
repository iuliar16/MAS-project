import time
import mesa
from mesa.visualization import SolaraViz, make_space_component


NUM_AGENTS = 10
GRID_SIZE = 10
SEED = 42
EMERGENCY_TIME = 10


class MonitorAgent(mesa.Agent):
    def __init__(self, model, emergency_time_seconds):
        super().__init__(model)
        self.model = model
        self.emergency_time = emergency_time_seconds
        self.emergency_triggered = False

    def step(self):
        elapsed = time.time() - self.model.start_time

        # If emergency hasn’t been triggered yet and enough seconds passed, mark monitor as triggered
        if not self.emergency_triggered and elapsed >= self.emergency_time:
            self.emergency_triggered = True
            self.model.emergency = True

            # notify all evac agents after 10 seconds
            for agent in self.model.active_agents:
                agent.emergency_triggered = True

class ExitAgent(mesa.Agent):
    def __init__(self, model):
        super().__init__(model)

class EvacAgent(mesa.Agent):
    def __init__(self, model):
        super().__init__(model)
        self.emergency_triggered = False
        # direction is used for constant walking before emergency
        self.direction = None

        self.state = "HELP"

        # reference to the guide agent being followed.
        self.following_agent = None
        # used to stop following after 10 seconds.
        self.follow_start_time = 0
        # dictionary to track who you recently asked
        self.asked_memory = {}

    # function used to loop over exits and see if they are in the agent radius (if they are close)
    def get_visible_exits(self, radius=3):
        visible_exits = []
        x, y = self.pos
        for exit_agent in self.model.exits:
            ex, ey = exit_agent.pos
            if abs(ex - x) <= radius and abs(ey - y) <= radius:
                visible_exits.append(exit_agent)
        return visible_exits

    # function that returns the closest exit by Manhattan distance (|dx| + |dy|).
    # returns the exit with smallest computed distance
    def closest_exit(self, exits):
        x, y = self.pos
        closest = min(exits, key=lambda e: abs(e.pos[0] - x) + abs(e.pos[1] - y))
        return closest

    def move_towards(self, target_pos):
        # computes direction deltas from current position to target
        x, y = self.pos
        tx, ty = target_pos
        dx = tx - x
        dy = ty - y

        # Builds up to two candidate next positions: one step closer in x or/and one step closer in y
        move_options = []
        if dx != 0:
            move_options.append((x + (1 if dx > 0 else -1), y))
        if dy != 0:
            move_options.append((x, y + (1 if dy > 0 else -1)))

        for nx, ny in move_options:
            # skip candidate if it’s outside the grid
            if self.model.grid.out_of_bounds((nx, ny)):
                continue

            # Get agents currently in that cell and if the cell is empty or its an exit cell, allow moving there
            cell_contents = self.model.grid.get_cell_list_contents((nx, ny))

            if len(cell_contents) == 0 or self.is_exit_cell((nx, ny)):
                self.model.grid.move_agent(self, (nx, ny))
                self.check_exit()
                return True

        return False

    def pick_random_direction(self):
        directions = [(0, 1), (0, -1), (1, 0), (-1, 0)]
        self.direction = self.random.choice(directions)

    # Calculate a fallback move when direct move is blocked
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

    # Checks if pos equals the position of any exit
    def is_exit_cell(self, pos):
        return any(exit_agent.pos == pos for exit_agent in self.model.exits)

    # if evac agent is on an exit remove it from the grid
    def check_exit(self):
        for exit_agent in self.model.exits:
            if self.pos == exit_agent.pos:
                self.model.grid.remove_agent(self)
                if self in self.model.active_agents:
                    self.model.active_agents.remove(self)
                return True
        return False

    def ask_neighbors(self):
        neighbors = self.model.grid.get_neighbors(self.pos, moore=True, radius=5, include_center=False)
        current_time = time.time()
        COOLDOWN = 3.0  # nu intrebam acelasi agent timp de 3 secunde

        for neighbor in neighbors:
            if isinstance(neighbor, EvacAgent) and neighbor in self.model.active_agents:
                # if never asked, treat last asked as time 0
                last_asked = self.asked_memory.get(neighbor, 0)
                if current_time - last_asked > COOLDOWN:
                    # Store that we asked this neighbor now
                    self.asked_memory[neighbor] = current_time
                    # If the neighbor can see an exit then he will be the guide
                    if neighbor.get_visible_exits():
                        return neighbor
        return None

    def do_random_constant_move(self):
        # after emergency = constant walking
        if self.direction is None:
            self.pick_random_direction()

        dx, dy = self.direction
        target = (self.pos[0] + dx, self.pos[1] + dy)

        moved = False
        if not self.model.grid.out_of_bounds(target):
            if len(self.model.grid.get_cell_list_contents(target)) == 0:
                self.model.grid.move_agent(self, target)
                moved = True

        if not moved:
            # if hit a wall or agent, change direction
            self.pick_random_direction()

    def step(self):
        # before emergency = random walking
        if not self.emergency_triggered:
            neighbors = self.model.grid.get_neighborhood(
                self.pos,
                moore=False,
                include_center=False,
                radius=1,
            )
            # get empty neighbor cells - if any, move to a random empty neighbor
            valid = [n for n in neighbors if not self.model.grid.get_cell_list_contents(n)]
            if valid:
                self.model.grid.move_agent(self, self.random.choice(valid))
            return

        visible_exits = self.get_visible_exits()
        # if agent can see exits, change state to Evacuating and stop following anyone
        if visible_exits:
            self.state = "EVACUATING"
            self.following_agent = None
        # If agent is following, then stop after 10 seconds of following (becomes HELP again)
        # or stop if the guide already exited (no longer active)
        if self.state == "FOLLOWING":
            if time.time() - self.follow_start_time > 10:
                self.state = "HELP"
                self.following_agent = None
            elif self.following_agent not in self.model.active_agents:  # if the guide has exited
                self.state = "HELP"
                self.following_agent = None

        # if state is Evacuating, then move to the closest exist
        if self.state == "EVACUATING":
            exit_agent = self.closest_exit(visible_exits)
            moved = self.move_towards(exit_agent.pos)

            # If direct path is blocked, try the best free step towards exit
            if not moved:
                target_cell = self.best_free_step_towards_exit(exit_agent)
                if target_cell:
                    self.model.grid.move_agent(self, target_cell)
                    self.check_exit()

        # If following someone, compute distance to them
        # if within 5 cells, move toward them
        # if too far, give up and revert to HELP
        elif self.state == "FOLLOWING":
            if self.following_agent and self.following_agent.pos:
                dist = abs(self.following_agent.pos[0] - self.pos[0]) + abs(self.following_agent.pos[1] - self.pos[1])
                if dist <= 5:
                    self.move_towards(self.following_agent.pos)
                else:
                    self.state = "HELP"

        # if state is help, try to find a guide by asking neighbors
        elif self.state == "HELP":
            guide = self.ask_neighbors()
            # if we found a guide, remember who it is and store follow start time
            if guide:
                self.state = "FOLLOWING"
                self.following_agent = guide
                self.follow_start_time = time.time()
            else:
                self.do_random_constant_move()

class GridModel(mesa.Model):
    def __init__(self, grid_size=GRID_SIZE, seed=SEED, emergency_time=EMERGENCY_TIME):
        super().__init__(seed=seed)

        self.grid = mesa.space.MultiGrid(grid_size, grid_size, torus=False)
        self.emergency = False
        self.start_time = time.time()
        self.active_agents = []
        self.monitor = MonitorAgent(self, emergency_time)

        self.exits = []

        exit_positions = [(0, 0), (grid_size - 1, grid_size - 1)]
        for pos in exit_positions:
            exit_agent = ExitAgent(self)
            self.grid.place_agent(exit_agent, pos)
            self.exits.append(exit_agent)

        # Create evac agents
        for _ in range(NUM_AGENTS):
            empty_cells = [
                (x, y)
                for (cell_content, (x, y)) in self.grid.coord_iter()
                if len(cell_content) == 0
            ]
            if empty_cells:
                init_pos = self.random.choice(empty_cells)
                agent = EvacAgent(self)
                self.grid.place_agent(agent, init_pos)
                self.active_agents.append(agent)


    def step(self):
        # Monitor checks if 10 seconds passed to give the alarm
        self.monitor.step()

        for agent in list(self.active_agents):
            agent.step()


def agent_portrayal(agent):
    if isinstance(agent, ExitAgent):
        return {
            "color": "green",
            "size": 140,
            "marker": "s",
        }
    if isinstance(agent, EvacAgent):
        color = "blue"
        if agent.emergency_triggered:
            if agent.state == "FOLLOWING":
                color = "yellow"
            elif agent.state == "EVACUATING":
                color = "red"
            else:
                color = "orange"
        return {
            "color": color,
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
        name="Evacuation Emergency Model",
    )

    page
