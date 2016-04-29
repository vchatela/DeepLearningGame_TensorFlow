import random
import os
import sys
import socket
import select
import time

from tools import algos
from tools import parser as pparser
from tools import communication as ccommunication
from tools import situation as ssituation
from tools import tools
from tools import think

import tensorflow as tf

from .base import Model
from ops import conv2d, max_pool_2x2

debug = tools.debug
ACTIONS = 4487

class GameModel(Model):
	"""Deep Game Network."""
	def __init__(self, sess,server_name, server_port):
		self.sess = sess
		self.build_model()
		self.init_server(server_name,server_port)
		
	def init_server(self,server_name,server_port):
		server_name = server_name
		server_port = int(server_port)

		# Connect to the server.
		server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		try:
			server.connect((server_name, server_port))
		except:
			print "Unable to connect"
			sys.exit(1)

		server_fd = server.makefile()

		self.situation = ssituation.Situation()
		self.parser = pparser.Parser(self.situation)
		self.communication = ccommunication.Communication(self.parser, server, server_fd)

	def build_model(self):
		# network weights
		W_conv1 = tf.Variable(tf.truncated_normal([8, 8, 4, 32], stddev = 0.01)) #valeurs bidons
		b_conv1 = tf.Variable(tf.constant(0.01, shape = [32]))

		# input layer
		#self.input_layer = tf.placeholder("float", [None, 80, 80, 4]) #valeurs bidons

		# hidden layers
		#self.h_fc1 = tf.nn.relu(tf.matmul(h_conv3_flat, W_fc1) + b_fc1)
		
		# readout layer
		#self.readout = tf.matmul(h_fc1, W_fc2) + b_fc2
		self.readout = b_conv1
	def play(self, learning_rate=0.001,
            checkpoint_dir="checkpoint",load=0):
		"""
		Args:
		  learning_rate: float, The learning rate [0.001]
		  checkpoint_dir: str, The path for checkpoints to be saved [checkpoint]
		"""
		situation = self.situation
		self.learning_rate = learning_rate
		self.checkpoint_dir = checkpoint_dir

		self.step = tf.Variable(0, trainable=False)
		
		sess = tf.Session()
		
		sess.run(tf.initialize_all_variables())
		sess.run(self.step.assign(0))

		one = tf.constant(1)
		new_value = tf.add(self.step, one)
		update = tf.assign(self.step, new_value)
		
		a = tf.placeholder("float", [None, ACTIONS])
		y = tf.placeholder("float", [None])
		
		#readout_action = tf.reduce_sum(tf.mul(self.readout, a), reduction_indices = 1)
		#cost = tf.reduce_mean(tf.square(y - readout_action))
		#train_step = tf.train.AdamOptimizer(learning_rate).minimize(cost)
		cost = 1
		
		
		if load :
			self.load(checkpoint_dir)

		start_time = time.time()
		
		

		nb = 0
		while 1:
			nb = nb + 1
			sess.run(update) #sess += 1
			
			self.communication.wait()

			debug("nb cities: %d" % len(situation.player_cities))
			debug("nb pieces: %d" % len(situation.player_pieces))

			situation.check()
			
			chunks = situation.split(8)
			
			## Define pieces in chunks
			for i in range(len(chunks)):
				chunk = chunks[i]
				print chunk
				print len(chunk)
				for q in range(len(chunk)):
					for r in range(len(chunk[q])):
						if chunk[q][r].visible == False:
							chunk[q][r] = 0
						else:
							if chunk[q][r].content == None:
								if chunk[q][r].terrain == ssituation.GROUND:
									chunk[q][r] = 1
								else:
									chunk[q][r] = 2
							else:
								if isinstance(chunk[q][r].content, ssituation.City):
									chunk[q][r] = 3
								elif isinstance(chunk[q][r].content, ssituation.OwnedCity):
									chunk[q][r] = 4 + chunk[q][r].content.owner # 4 et 5 !!!
								else:
									chunk[q][r] = 6 + chunk[q][r].content.piece_type + chunk[q][r].content.owner * len(situation.pieces_types)
									
			# Define cities production
			
			for city_id in situation.player_cities:
				think.choose_relevant_random_production(situation, self.communication, city_id)
			
			# Define pieces action
			
			piece_ids = situation.player_pieces.keys()
			for piece_id in piece_ids:
				piece = situation.player_pieces[piece_id]
				loc = situation.get_player_piece_location(piece_id)
				depth = situation.pieces_types[piece.piece_type].speed
				def crossable(a):
					qa, ra = a
					return situation.is_in_map((qa, ra)) and \
							situation.can_player_piece_be_on(piece_id, (qa, ra)) and \
							situation.is_tile_none((qa, ra))
				def neighbors(a):
					qa, ra = a
					result = []
					for direction in algos.directions:
						qd, rd = direction
						qb, rb = qa + qd, ra + rd
						if situation.is_in_map((qb, rb)) and situation.can_player_piece_be_on(piece_id, (qb, rb)):
							result.append( (qb, rb) )
					return result
				def cost(x, y):
					return 1
				heuristic = situation.get_tiles_distance
				destinations, came_from = algos.breadth_first_search_all(loc, depth, neighbors, cost, heuristic, crossable)
				if len(destinations) > 0:
					destination = random.choice(destinations)
					self.communication.action("moves %d %d %d" % (piece_id, destination[0], destination[1]))
					
			# Show situation 
			if nb % 10 == 0:
				situation.show()
			# Save checkpoint each 1000 steps
			if nb != 0 and nb % 1000 == 0:
				self.save(checkpoint_dir, step)
			# Show current progress
			step = sess.run(self.step)
			if nb % 1000 == 1:
				print("Epoch: [%2d] time: %4.4f, loss: %.8f" % (step, time.time() - start_time, cost))
			self.communication.end_turn()
