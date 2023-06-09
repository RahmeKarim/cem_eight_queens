# -*- coding: utf-8 -*-
"""FourQueens.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1sNoKUu5Gz3sE7ACG9UTrha53EaJTFdp2
"""

import numpy as np

import torch
import torch.nn as nn
import torch.optim as optim

import torch.nn.functional as F

from torch.utils.tensorboard import SummaryWriter

import matplotlib.pyplot as plt 
import math

CHESSBOARD_SIZE = 8

if torch.cuda.is_available():      
    device = torch.device("cuda")
else:
    device = torch.device("cpu")

class PolicyNN(nn.Module):
  def __init__(self, input_layer_size, hidden_layer_sizes, output_layer_size):
    super(PolicyNN, self).__init__()
    self.layers = nn.Sequential(
      nn.Linear(input_layer_size, hidden_layer_sizes[0]),
      nn.Tanh(),
      nn.Linear(hidden_layer_sizes[0], hidden_layer_sizes[1]),
      nn.Tanh(),
      nn.Linear(hidden_layer_sizes[1], hidden_layer_sizes[2]),
      nn.Tanh(),
      nn.Linear(hidden_layer_sizes[2], output_layer_size)
    )

  def forward(self, x):
    x = self.layers(x)
    return x

import gym
from gym.spaces import Graph, Box, Discrete

class QueensEnv(gym.Env):
  def __init__(self, size=4):
    super(QueensEnv, self).__init__()

    self.observation_space = Box(low=0, high=size-1, shape=(size, ), dtype=int)
    self.action_space = Discrete(size-1)

    self.size = size
    self.step_count = 0
    self.solutions = []

  def _calculate_reward(self):
    reward = 0

    for i in range(self.current_step):
      for j in range(i + 1, self.current_step):
        # Check for queens in the same row or on the same diagonal
        if (self.observation[i] == self.observation[j] or
          self.observation[i] - self.observation[j] == i - j or
          self.observation[i] - self.observation[j] == j - i):
          reward -= 1

    # Provide large reward when all queens are safe
    if reward == 0 and self.current_step == self.size:
      reward += self.size ** 2

      exists = 0

      for sol in self.solutions:
        if np.array_equal(sol, self.observation):
          exists = 1
        
      if exists == 0:
        self.solutions.append(self.observation)
        print("Solution:", self.observation)

    return reward

  def step(self, action):
    self.observation[self.current_step] = action
    self.current_step += 1

    reward = self._calculate_reward()
    done = self.current_step == self.size
    return self.observation.copy(), reward, done, {}


  def reset(self):
    self.observation = np.random.choice(self.size, size=self.size, replace=False)
    self.current_step = 0
    return self.observation.copy()

  def close(self):
    pass

def select_action(obs, net):
  sm = nn.Softmax(dim=0)

  input = torch.FloatTensor(obs).to(device)

  output = net(input)

  action_probabilities_v = sm(output)

  action_probabilities = action_probabilities_v.cpu().data.numpy()
        
  action = np.random.choice(CHESSBOARD_SIZE, p=action_probabilities)

  return action

from collections import namedtuple

Episode = namedtuple('Episode', field_names=['reward', 'steps'])
EpisodeStep = namedtuple('EpisodeStep', field_names=['observation', 'action'])

def iterate_batches(env, net, batch_size):
  batch = []
  episode_reward = 0.0
  episode_steps = []
  obs = env.reset()
  
  while True:
    action = select_action(obs, net);

    next_obs, reward, is_done, _ = env.step(action)

    episode_reward += reward

    step = EpisodeStep(observation=obs, action=action)
    episode_steps.append(step)

    if is_done:
      e = Episode(reward=episode_reward, steps=episode_steps)
      batch.append(e)

      episode_reward = 0.0
      episode_steps = []
      
      next_obs = env.reset()

      if len(batch) == batch_size:
        yield batch
        batch = []

    obs = next_obs

def filter_batch(batch, percentile):
  rewards = list(map(lambda s: s.reward, batch))
  reward_bound = np.percentile(rewards, percentile)
  reward_mean = float(np.mean(rewards))

  train_obs = []
  train_act = []

  for episode in batch:
    if episode.reward < reward_bound:
      continue
    train_obs.extend(map(lambda step: step.observation, episode.steps))
    train_act.extend(map(lambda step: step.action, episode.steps))

  train_obs_v = torch.FloatTensor(train_obs).to(device)
  train_act_v = torch.LongTensor(train_act).to(device)

  return train_obs_v, train_act_v, reward_bound, reward_mean

env = QueensEnv(size=CHESSBOARD_SIZE)

INPUT_LAYER_SIZE = CHESSBOARD_SIZE
HIDDEN_LAYER_SIZES = [128, 64, 8] # keep small to avoid memorization
OUTPUT_LAYER_SIZE = CHESSBOARD_SIZE

policyNet = PolicyNN(INPUT_LAYER_SIZE, HIDDEN_LAYER_SIZES, OUTPUT_LAYER_SIZE)
policyNet.to(device)


objective = nn.CrossEntropyLoss()
optimizer = optim.Adam(params=policyNet.parameters(), lr=0.0001)


writer = SummaryWriter(comment="-graph")

BATCH_SIZE = 1000
PERCENTILE = 90

n_actions = CHESSBOARD_SIZE

for iter_no, batch in enumerate(iterate_batches(env, policyNet, BATCH_SIZE)):
  obs_v, acts_v, reward_b, reward_m = filter_batch(batch, PERCENTILE)
  optimizer.zero_grad()

  obs_v = obs_v.to(device)
  acts_v = acts_v.to(device)

  action_scores_v = policyNet(obs_v)

  acts_v_one_hot = F.one_hot(acts_v, n_actions).float().to(device)

  loss_v = objective(action_scores_v, acts_v_one_hot)
  loss_v.backward()
  optimizer.step()

  if iter_no % 100 == 0:
    print("%d: loss=%.3f, reward_mean=%.1f, rw_bound=%.1f" % (
      iter_no, loss_v.item(), reward_m, reward_b))
    
  writer.add_scalar("loss", loss_v.item(), iter_no)
  writer.add_scalar("reward_bound", reward_b, iter_no)
  writer.add_scalar("reward_mean", reward_m, iter_no)

  if len(env.solutions) == 92:
    print("Solved!")
    break

writer.close()