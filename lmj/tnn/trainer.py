# Copyright (c) 2012 Leif Johnson <leif@leifjohnson.net>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

'''This file contains optimization methods for neural networks.'''

import logging
import numpy
import theano
import theano.tensor as TT
import sys


class Trainer(object):
    '''This is an abstract base class for all trainers.'''

    def train(self, train_set, valid_set=None):
        raise NotImplementedError

    def evaluate(self, test_set):
        return [self.f_eval(*i) for i in test_set]


class SGD(Trainer):
    '''Stochastic gradient descent network trainer.'''

    def __init__(self, network, **kwargs):
        self.vf = kwargs.get('validate', 3)
        self.epochs = kwargs.get('epochs', sys.maxint)
        decay = kwargs.get('decay', 1)
        m = kwargs.get('momentum', 0)
        lr = kwargs.get('learning_rate', 0.1)

        J = network.J(**kwargs)
        t = theano.shared(numpy.cast['float32'](0), name='t')
        updates = {t: t + 1}
        for param in network.params:
            grad = TT.grad(J, param)
            heading = theano.shared(
                numpy.zeros_like(param.get_value(borrow=True)),
                name='g_%s' % param.name)
            updates[param] = param + heading
            updates[heading] = m * heading - lr * (decay ** t) * grad

        costs = [J] + network.monitors
        self.f_eval = theano.function(network.inputs, costs)
        self.f_rate = theano.function([], [lr * (decay ** t)])
        self.f_train = theano.function(network.inputs, costs, updates=updates)
        #theano.printing.pydotprint(
        #    theano.function(network.inputs, [J]), '/tmp/theano-network.png')

    def train(self, train_set, valid_set=None):
        for u in xrange(self.epochs):
            acc = [self.f_train(*i) for i in train_set]
            fmt = 'epoch %i[%.2g]: train %s'
            args = (u, self.f_rate()[0], numpy.mean(acc, axis=0))
            if valid_set is not None and self.vf > 0 and u % self.vf == 0:
                acc = [self.f_eval(*i) for i in valid_set]
                fmt += ' valid %s'
                args += (numpy.mean(acc, axis=0), )
            logging.info(fmt, *args)


class HF(Trainer):
    '''The hessian free trainer shells out to an external implementation.

    hf.py was implemented by Nicholas Boulanger-Lewandowski and developed by
    Martens and Sutskever. If you don't have a copy of the module handy, this
    class will attempt to download it from github.
    '''

    URL = 'https://raw.github.com/boulanni/theano-hf/master/hf.py'

    def __init__(self, network, **kwargs):
        try:
            import hf
        except:
            # if hf failed to import, try downloading it and saving it locally.
            import os, urllib
            logging.error('hf import failed, attempting to download %s', HF.URL)
            path = os.path.join(os.getcwd(), 'hf.py')
            urllib.urlretrieve(HF.URL, path)
            logging.error('downloaded hf code to %s', path)
            del os
            del urllib
            import hf

        c = [network.J(**kwargs)] + network.monitors
        self.f_eval = theano.function(network.inputs, c)
        self.cg_set = kwargs.pop('cg_set')
        self.opt = hf.hf_optimizer(network.params, network.inputs, network.y, c)

        # fix mapping from kwargs into a dict to send to the hf optimizer
        kwargs['num_updates'] = kwargs.pop('epochs', sys.maxint)
        kwargs['validation_frequency'] = kwargs.pop('validate', sys.maxint)
        for k in set(kwargs) - set(self.opt.train.im_func.func_code.co_varnames[1:]):
            kwargs.pop(k)
        self.kwargs = kwargs

    def train(self, train_set, valid_set=None):
        self.opt.train(train_set, self.cg_set, validation=valid_set, **self.kwargs)


class FORCE(Trainer):
    '''FORCE is a training method for recurrent nets by Sussillo & Abbott.

    The code here still needs implementation and testing.
    '''

    def __init__(self, network, **kwargs):
        W_in, W_pool, W_out = network.weights

        n = len(W_pool.get_value(shared=True))
        alpha = kwargs.get('learning_rate', 1. / n)
        P = theano.shared(numpy.eye(n).astype(FLOAT) * alpha)

        k = T.dot(P, network.state)
        rPr = 1 + T.dot(network.state, k)
        J = network.J(**kwargs)

        updates = {}
        updates[P] = P - T.dot(k, k) / rPr
        updates[W_pool] = W_pool - J * k / rPr
        updates[W_out] = W_out - J * k / rPr
        updates[b_out] = b_out - alpha * T.grad(J, b_out)

        costs = [J] + network.monitors
        self.f_eval = theano.function(network.inputs, costs)
        self.f_train = theano.function(network.inputs, costs, updates=updates)

    def train(self, train_set, valid_set=None):
        # TODO !
        pass
