import unittest
from threading import Thread

from util.singleton import Singleton


class SingletonTestClass(metaclass = Singleton):

    pass


class SingletonTest(unittest.TestCase):

    def test_instance_safety(self):
        self.addCleanup(Singleton._instances.pop, SingletonTestClass, None)
        instances = []

        def create_instance():
            instances.append(SingletonTestClass())

        threads = [Thread(target = create_instance) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(len(instances), 10)
        # check if it's the same instance or not
        for instance in instances:
            self.assertIs(instance, instances[0])
