import copy
from itertools import product
from collections import Hashable

import numpy as np
import pandas as pd

import gym

from tiles.tiles3 import tiles, IHT


class Dict(dict):
    """
    A dictionary subclass which returns the key value if not already in the dict
    """

    def __init__(self, encoder=None):
        super(Dict, self).__init__()
        self.encoder = encoder

    def __setitem__(self, key, value):
        if self.encoder is not None:
            key = self.encoder(key)
        elif not isinstance(key, Hashable):
            key = tuple(key)
        super(Dict, self).__setitem__(key, value)

    def __getitem__(self, key):
        self._key = copy.deepcopy(key)
        if self.encoder is not None:
            val = self.encoder(key)
            return val
        elif not isinstance(key, Hashable):
            key = tuple(key)
        return super(Dict, self).__getitem__(key)

    def __missing__(self, key):
        return self._key


def tile_state_space(
    env,
    env_stats,
    n_tilings,
    obs_max=None,
    obs_min=None,
    state_action=False,
    grid_size=(4, 4),
):
    """
    Return a function to encode the continous observations generated by `env`
    in terms of a collection of `n_tilings` overlapping tilings (each with
    dimension `grid_size`) of the state space.

    Arguments
    ---------
    env : gym.wrappers.time_limit.TimeLimit
        An openAI environment
    n_tilings : int
        The number of overlapping tilings to use. Should be a power of 2. This
        determines the dimension of the discretized tile-encoded state vector
    obs_max : float or np.ndarray (default: None)
        The value to treat as the max value of the observation space when
        calculating the grid widths. If `None`, use env.observation_space.high
    obs_min : float or np.ndarray (default: None)
        The value to treat as the min value of the observation space when
        calculating the grid widths. If `None`, use env.observation_space.low
    state_action : bool (default: False)
        Whether to use tile coding to encode state-action values (True) or just
        state values (False)
    grid_size : list of length 2
        A list of ints representing the coarseness of the tilings. E.g., a
        `grid_size` of [4, 4] would mean each tiling consisted of a 4x4 tile
        grid

    Returns
    -------
    encode_obs_as_tile : function
        A function which takes as input continous observation vector and
        returns a set of the indices of the active tiles in the tile coded
        observation space
    n_states : int
        An integer reflecting the total number of unique states possible under
        this tile coding regimen
    """
    obs_max = np.nan_to_num(env.observation_space.high) if obs_max is None else obs_max
    obs_min = np.nan_to_num(env.observation_space.low) if obs_min is None else obs_min

    if state_action:
        if env_stats["tuple_action"]:
            n = [space.n - 1.0 for space in env.action_spaces.spaces]
        else:
            n = [env.action_space.n]

        obs_max = np.concatenate([obs_max, n])
        obs_min = np.concatenate([obs_min, np.zeros_like(n)])

    obs_range = obs_max - obs_min
    scale = 1.0 / obs_range

    # scale (state-)observation vector
    scale_obs = lambda obs: obs * scale

    n_tiles = np.prod(grid_size) * n_tilings
    n_states = np.prod([n_tiles - i for i in range(n_tilings)])
    iht = IHT(16384)

    def encode_obs_as_tile(obs):
        obs = scale_obs(obs)
        return tuple(tiles(iht, n_tilings, obs))

    return encode_obs_as_tile, n_states


def get_gym_environs():
    """
    List all valid gym environment ids
    """
    return [e.id for e in gym.envs.registry.all()]


def get_gym_stats():
    df = []
    for e in gym.envs.registry.all():
        print(e.id)
        df.append(env_stats(gym.make(e.id)))
    cols = [
        "id",
        "continuous_actions",
        "continuous_observations",
        "action_dim",
        #  "action_ids",
        "deterministic",
        "multidim_actions",
        "multidim_observations",
        "n_actions_per_dim",
        "n_obs_per_dim",
        "obs_dim",
        #  "obs_ids",
        "seed",
        "tuple_actions",
        "tuple_observations",
    ]
    return pd.DataFrame(df)[cols]


def is_tuple(env):
    """
    A Tuple space is a tuple of *several* (possibly multidimensional)
    action/observation spaces. For our purposes, a tuple space is necessarily
    multidimensional.
    """
    tuple_space, dict_space = gym.spaces.Tuple, gym.spaces.dict.Dict
    tuple_action = isinstance(env.action_space, (tuple_space, dict_space))
    tuple_obs = isinstance(env.observation_space, (tuple_space, dict_space))
    return tuple_action, tuple_obs


def is_multidimensional(env):
    """
    A multidimensional space is any space whose actions / observations have
    more than one element in them. This includes Tuple spaces, but also
    includes single action/observation spaces with several dimensions.
    """
    md_action, md_obs = True, True
    tuple_action, tuple_obs = is_tuple(env)
    if not tuple_action:
        act = env.action_space.sample()
        md_action = isinstance(act, (list, tuple, np.ndarray)) and len(act) > 1

    if not tuple_obs:
        OS = env.observation_space
        obs = OS.low if "low" in dir(OS) else OS.sample()  # sample causes problems
        md_obs = isinstance(obs, (list, tuple, np.ndarray)) and len(obs) > 1
    return md_action, md_obs, tuple_action, tuple_obs


def is_continuous(env, tuple_action, tuple_obs):
    """
    Check if the observation and action spaces are continuous
    """
    Continuous = gym.spaces.box.Box
    if tuple_obs:
        spaces = env.observation_space.spaces
        cont_obs = all([isinstance(s, Continuous) for s in spaces])
    else:
        cont_obs = isinstance(env.observation_space, Continuous)

    if tuple_action:
        spaces = env.action_space.spaces
        cont_action = all([isinstance(s, Continuous) for s in spaces])
    else:
        cont_action = isinstance(env.action_space, Continuous)
    return cont_action, cont_obs


def action_stats(env, md_action, cont_action):
    """
    Get information on env's action space
    """
    if cont_action:
        action_dim = 1
        action_ids = None
        n_actions_per_dim = [np.inf]

        if md_action:
            action_dim = env.action_space.shape[0]
            n_actions_per_dim = [np.inf for _ in range(action_dim)]
    else:
        if md_action:
            n_actions_per_dim = [
                space.n if hasattr(space, "n") else np.inf
                for space in env.action_space.spaces
            ]
            action_ids = (
                None
                if np.inf in n_actions_per_dim
                else list(product(*[range(i) for i in n_actions_per_dim]))
            )
            action_dim = len(n_actions_per_dim)
        else:
            action_dim = 1
            n_actions_per_dim = [env.action_space.n]
            action_ids = list(range(n_actions_per_dim[0]))
    return n_actions_per_dim, action_ids, action_dim


def obs_stats(env, md_obs, cont_obs):
    """
    Get information on env's observation space
    """
    if cont_obs:
        obs_ids = None
        obs_dim = env.observation_space.shape[0]
        n_obs_per_dim = [np.inf for _ in range(obs_dim)]
    else:
        if md_obs:
            n_obs_per_dim = [
                space.n if hasattr(space, "n") else np.inf
                for space in env.observation_space.spaces
            ]
            obs_ids = (
                None
                if np.inf in n_obs_per_dim
                else list(product(*[range(i) for i in n_obs_per_dim]))
            )
            obs_dim = len(n_obs_per_dim)
        else:
            obs_dim = 1
            n_obs_per_dim = [env.observation_space.n]
            obs_ids = list(range(n_obs_per_dim[0]))

    return n_obs_per_dim, obs_ids, obs_dim


def env_stats(env):
    """
    Compute statistics for the current environment.

    Parameters
    ----------
    env : gym.wrappers or gym.envs instance
        The environment to run the agent on

    Returns
    -------
    env_info : dict
        A dictionary containing information about the action and observation
        spaces of `env`
    """
    md_action, md_obs, tuple_action, tuple_obs = is_multidimensional(env)
    cont_action, cont_obs = is_continuous(env, tuple_action, tuple_obs)

    n_actions_per_dim, action_ids, action_dim = action_stats(
        env, md_action, cont_action
    )
    n_obs_per_dim, obs_ids, obs_dim = obs_stats(env, md_obs, cont_obs)

    env_info = {
        "id": env.spec.id,
        "seed": env.spec.seed if "seed" in dir(env.spec) else None,
        "deterministic": bool(~env.spec.nondeterministic),
        "tuple_actions": tuple_action,
        "tuple_observations": tuple_obs,
        "multidim_actions": md_action,
        "multidim_observations": md_obs,
        "continuous_actions": cont_action,
        "continuous_observations": cont_obs,
        "n_actions_per_dim": n_actions_per_dim,
        "action_dim": action_dim,
        "n_obs_per_dim": n_obs_per_dim,
        "obs_dim": obs_dim,
        "action_ids": action_ids,
        "obs_ids": obs_ids,
    }

    return env_info
