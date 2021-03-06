import json
import sys
import time
from hashlib import sha256
from threading import Thread

import requests as http

from blockchain import NODES
from blockchain.core.transaction import Transaction, QueueTransaction

BLOCK_TRANSACTION = 5
BLOCK_DIFFICULTY = 6


class Block:

    @staticmethod
    def parse(json):
        block = Block(index=json['index'], previous_hash=json['previous_hash'])
        block.difficulty = json['difficulty']
        block.timestamp = json['timestamp']
        block.block_hash = json['block_hash']
        block.nonce = json['nonce']

        for item in json['transactions']:
            transaction = Transaction.parse(item)
            if transaction:
                block.__transaction.append(transaction)

        return block

    def to_json(self):
        transactions = [item.to_json() for item in self.__transaction]
        return json.dumps({
            'index', self.index,
            'previous_hash', self.previous_hash,
            'difficulty', self.difficulty,
            'timestamp', self.timestamp,
            'block_hash', self.block_hash,
            'nonce', self.nonce,
            'transactions', transactions
        })

    def __init__(self, index, previous_hash):
        self.index = index
        self.previous_hash = previous_hash
        self.difficulty = BLOCK_DIFFICULTY

        self.__transaction = list()
        self.timestamp = time.time() * 1000.0
        self.block_hash = ""
        self.nonce = 0

        if not isinstance(index, int):
            raise Exception('index is not integer')

        if not isinstance(previous_hash, str):
            raise Exception('previous_hash is not string')

    def add_transaction(self, transaction):
        if not isinstance(transaction, QueueTransaction):
            raise Exception("transaction is not QueueTransaction")

        if len(self.__transaction) < BLOCK_TRANSACTION:
            self.__transaction.append(transaction)
            return True

        return False

    def pow(self):
        try:
            transaction_list = [tx.hash_tx() for tx in self.__transaction]
            data_block = json.dumps([self.index,
                                     self.previous_hash,
                                     self.difficulty,
                                     transaction_list,
                                     self.timestamp,
                                     self.nonce])

            block_hash = sha256(data_block.encode('utf-8')).hexdigest()
            return block_hash.startswith('0' * self.difficulty)
        except:
            return False

    def is_valid(self):
        return self.block_hash.startswith('0' * self.difficulty)

    def start_find_pow(self):
        transaction_list = [tx.hash_tx() for tx in self.__transaction]

        start = time.time()

        for nonce in range(sys.maxsize):
            self.nonce = nonce

            data_block = json.dumps([self.index,
                                     self.previous_hash,
                                     self.difficulty,
                                     transaction_list,
                                     self.timestamp,
                                     self.nonce])

            self.block_hash = sha256(data_block.encode('utf-8')).hexdigest()

            if self.is_valid():
                print('block {} mined in {} second => {}'
                      .format(self.index, (time.time() - start), self.block_hash))
                return True

        return False


class Blockchain:
    def __init__(self):
        self.unconfirmed_transaction = list()
        self.chains = list()
        self.chains.append(self.genesis_block())

    def genesis_block(self):
        new_block = Block(index=0, previous_hash='0')
        new_block.difficulty = 0
        new_block.timestamp = 0
        new_block.block_hash = '0'
        new_block.nonce = 0
        return new_block

    def add_block(self, block):
        if not isinstance(block, Block):
            return False

        if self.last_chain().index == (block.index - 1) \
                and block.is_valid() and block.pow():
            self.chains.append(block)
            return True

        return False

    def add_transaction(self, transaction):
        self.unconfirmed_transaction.append(transaction)
        return True

    def last_chain(self):
        return self.chains[-1]

    def mine(self):
        all_txs = self.unconfirmed_transaction.copy()
        last_block = self.last_chain()

        new_block = Block(index=last_block.index + 1, previous_hash=last_block.block_hash)
        removing_txs = list()

        for index, tx in enumerate(all_txs):
            if new_block.add_transaction(tx):
                removing_txs.append(tx)
            else:
                break

        if new_block.start_find_pow():
            self.synchronization()
            if self.add_block(new_block):

                if not self.send_block_all_nodes(new_block):
                    print("######### ERROR NODE NOT ADDED BLOCK #########")

                for index in removing_txs:
                    self.unconfirmed_transaction.pop(index)
            else:
                print('cannot add block in chain')
        else:
            print('not find block hash')

        Thread(target=self.mine).start()

    def synchronization(self):
        last_block = self.last_chain()
        for nod in NODES:
            try:
                response = http.get('{}/{}'.format(nod, 'node&load_last_block'))
                if response.ok:
                    node_last_block = Block.parse(json.loads(response.text))

                    if node_last_block.index > last_block:
                        self.load_all_blocks(nod)
            except:
                pass

    def load_all_blocks(self, node):
        try:
            data_json = {'start_index': self.last_chain().index}
            resp = http.post('{}/{}'.format(node, 'node&load_blocks'), json=data_json)
            if resp.ok:
                blocks = [Block.parse(item) for item in json.loads(resp.text)]
                for b in blocks:
                    if not self.add_block(b):
                        print('node block not added in blockchain, block have problem')
                        return
        except:
            print('error load_all_blocks')

    def send_block_all_nodes(self, block):
        block_json = json.loads(block.to_json())
        for nod in NODES:
            try:
                resp = http.post('{}/{}'.format(nod, 'node&add_new_block'), json=block_json)
                if resp.ok:
                    return 'S' == resp.text
                else:
                    self.synchronization()
            except:
                print('error send_block_all_nodes')
            return True
