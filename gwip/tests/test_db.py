
# This file is part of gwip.
#
# This work is licensed under the Creative Commons Attribution-NonCommercial
# 4.0 International License. To view a copy of this license, visit
# http://creativecommons.org/licenses/by-nc/4.0/ or send a letter to Creative
# Commons, PO Box 1866, Mountain View, CA 94042, USA.


import time
import sqlite3
import unittest
from datetime import datetime
from tempfile import TemporaryDirectory

from ..db.utils import *
from ..db.utils import _create_db_connection


__author__ = "Louis-Philippe Lemieux Perreault"
__copyright__ = "Copyright 2014, Beaulieu-Saucier Pharmacogenomics Centre"
__license__ = "Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)"


class TestDB(unittest.TestCase):

    def setUp(self):
        """Setup the tests."""
        # Creating the temporary directory
        self.output_dir = TemporaryDirectory(prefix="gwip_test_")

        # We need to create an empty database
        self.db_name = create_task_db(self.output_dir.name)

        # We're going to add thee entries
        self.creation_times = []
        self.task_names = []
        for i in range(4):
            task_name = "dummy_task_{}".format(i + 1)
            self.creation_times.append(datetime.now())
            create_task_entry(task_name, self.db_name)
            self.task_names.append(task_name)

    def tearDown(self):
        """Finishes the test."""
        # Deleting the output directory
        self.output_dir.cleanup()

    def test_create_task_db(self):
        """Tests the 'create_task_db' function."""
        # The DB should already be created, so we connect to it
        conn = sqlite3.connect(
            self.db_name,
            timeout=360,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )
        c = conn.cursor()

        # Getting all the tables
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = c.fetchall()

        # There should only be one table (and one column)
        self.assertEqual(1, len(tables))
        self.assertEqual(1, len(tables[0]))

        # The only value should have name=gwip_task
        self.assertEqual("gwip_task", tables[0][0])

        # Checking the columns (name, type, notnull, default, primary)
        expected_columns = {
            "name": ("name", "TEXT", 0, None, 1),
            "launch": ("launch", "TIMESTAMP", 0, None, 0),
            "start": ("start", "TIMESTAMP", 0, None, 0),
            "end": ("end", "TIMESTAMP", 0, None, 0),
            "completed": ("completed", "INT", 0, None, 0),
        }
        c.execute("PRAGMA table_info(gwip_task)")
        col_names = set()
        for result in c.fetchall():
            # Getting the name of the column
            col_name = result[1]
            col_names.add(col_name)

            # Checking the content of the columns
            self.assertEqual(expected_columns[col_name], result[1:])

        # Checking we have all columns
        if len((col_names & set(expected_columns.keys())) - col_names) != 0:
            self.fail("not all DB columns are present")

    def test_create_db_connection(self):
        """Tests the '_create_db_connection' function."""
        # Creating the connection
        conn, c = _create_db_connection(self.db_name)

        # Checking that the table 'gwip_task' exists
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        self.assertEqual("gwip_task", c.fetchone()[0])

        # Closing the connection
        conn.close()

    def test_check_task_completion(self):
        """Tests the 'check_task_completion' function."""
        # Marking the first and fourth tasks as completed
        start = self.creation_times[3].timestamp()
        now = datetime.now().timestamp()
        mark_task_completed(self.task_names[0], self.db_name)
        mark_drmaa_task_completed(self.task_names[3], start, start, now,
                                  self.db_name)

        # Marking the second one as incomplete
        mark_task_incomplete(self.task_names[1], self.db_name)

        # Checking the values
        self.assertTrue(check_task_completion(self.task_names[0],
                                              self.db_name))
        self.assertFalse(check_task_completion(self.task_names[1],
                                               self.db_name))
        self.assertFalse(check_task_completion(self.task_names[2],
                                               self.db_name))
        self.assertTrue(check_task_completion(self.task_names[3],
                                              self.db_name))

        # Setting a completely random value for the third task
        conn, c = _create_db_connection(self.db_name)
        c.execute("UPDATE gwip_task SET completed='foo' WHERE name=?",
                  (self.task_names[3], ))
        conn.commit()
        conn.close()
        self.assertFalse(check_task_completion(self.task_names[3],
                                               self.db_name))

    def test_create_task_entry(self):
        """Tests the 'create_task_entry' function."""
        # The task that will be modified
        modified_task = self.task_names[0]

        # Three tasks should have been created
        conn, c = _create_db_connection(self.db_name)

        # Fetching all the tasks
        c.execute("SELECT name FROM gwip_task")
        results = [r[0] for r in c.fetchall()]
        self.assertEqual(self.task_names, results)

        # Checking that the times are the same
        c.execute("SELECT name, launch, start, end, completed FROM gwip_task")
        results = c.fetchall()
        iteration = zip(self.task_names, self.creation_times, results)
        for task_name, expected_time, result in iteration:
            # The observed values
            o_name, o_launch, o_start, o_end, o_completed = result

            # The name should be the same
            self.assertEqual(task_name, o_name)

            # The launch and start times should be the same (to first decimal)
            self.assertEqual(o_launch, o_start)
            t_delta = (o_launch - expected_time).total_seconds()
            self.assertAlmostEqual(0, t_delta, places=0)

            # End and completed should be none
            self.assertTrue(o_end is None)
            self.assertTrue(o_completed is None)

        # We are going to relaunch a task after 3 seconds
        time.sleep(3)
        now = datetime.now()
        create_task_entry(modified_task, self.db_name)
        c.execute("SELECT name, launch, start, end, completed FROM gwip_task")
        results = c.fetchall()
        iteration = zip(self.task_names, self.creation_times, results)
        for task_name, expected_time, result in iteration:
            # The expected values
            o_name, o_launch, o_start, o_end, o_completed = result

            # The name should be the same
            self.assertEqual(task_name, o_name)

            # The expected time is different for the first task
            if task_name == modified_task:
                expected_time = now

            # The launch and start times should be the same (to milliseconds)
            self.assertEqual(o_launch, o_start)
            t_delta = (o_launch - expected_time).total_seconds()
            self.assertAlmostEqual(0, t_delta, places=0)

            # End and completed should be none (except for first task)
            self.assertTrue(o_end is None)

            if task_name == modified_task:
                self.assertEqual(0, o_completed)
            else:
                self.assertTrue(o_completed is None)

        # Closing the connection
        conn.close()

    def test_mark_task_completed(self):
        """Tests the 'mark_task_completed' function."""
        # The task that will be modified
        modified_task = self.task_names[0]

        # We are going to mark the first task as completed after 3 seconds
        time.sleep(3)
        completion_time = datetime.now()
        mark_task_completed(modified_task, self.db_name)

        # Creating the connection
        conn, c = _create_db_connection(self.db_name)

        # Checking that the times are the same
        c.execute("SELECT name, launch, start, end, completed FROM gwip_task")
        results = c.fetchall()
        iteration = zip(self.task_names, self.creation_times, results)
        for task_name, expected_time, result in iteration:
            # The observed values
            o_name, o_launch, o_start, o_end, o_completed = result

            # The name should be the same
            self.assertEqual(task_name, o_name)

            # The launch and start times should be the same (to first decimal)
            self.assertEqual(o_launch, o_start)
            t_delta = (o_launch - expected_time).total_seconds()
            self.assertAlmostEqual(0, t_delta, places=0)

            # End and completed should be none unless it's the first task
            if task_name != modified_task:
                self.assertTrue(o_end is None)
                self.assertTrue(o_completed is None)
            else:
                # The task should be completed
                self.assertEqual(1, o_completed)

                # Time difference between completion times
                t_delta = (o_end - completion_time).total_seconds()
                self.assertAlmostEqual(0, t_delta, places=0)

                # Time difference between start and end should be 3
                t_delta = (o_end - o_start).total_seconds()
                self.assertAlmostEqual(3, t_delta, places=0)

        conn.close()

    def test_mark_task_incomplete(self):
        """Tests the 'mark_task_incomplete' function."""
        # Marking an incomplete task shouldn't change its values (except
        # completed)
        modified_task = self.task_names[0]
        mark_task_incomplete(modified_task, self.db_name)

        # Creating the connection
        conn, c = _create_db_connection(self.db_name)

        # Checking that the times are the same
        c.execute("SELECT name, launch, start, end, completed FROM gwip_task")
        results = c.fetchall()
        iteration = zip(self.task_names, self.creation_times, results)
        for task_name, expected_time, result in iteration:
            # The observed values
            o_name, o_launch, o_start, o_end, o_completed = result

            # The name should be the same
            self.assertEqual(task_name, o_name)

            # The launch and start times should be the same (to first decimal)
            self.assertEqual(o_launch, o_start)
            t_delta = (o_launch - expected_time).total_seconds()
            self.assertAlmostEqual(0, t_delta, places=0)

            # End and completed should be none unless it's the first task
            self.assertTrue(o_end is None)
            if task_name != modified_task:
                self.assertTrue(o_completed is None)
            else:
                # The task should be completed
                self.assertEqual(0, o_completed)

        # Now, marking a task as completed, waiting for 3 seconds and mark it
        # as incomplete
        modified_task = self.task_names[1]
        completion_time = datetime.now()
        mark_task_completed(modified_task, self.db_name)
        time.sleep(3)
        mark_task_incomplete(modified_task, self.db_name)

        # Checking that the times are the same
        c.execute("SELECT name, launch, start, end, completed FROM gwip_task")
        results = c.fetchall()
        iteration = zip(self.task_names, self.creation_times, results)
        for task_name, expected_time, result in iteration:
            # The observed values
            o_name, o_launch, o_start, o_end, o_completed = result

            # The name should be the same
            self.assertEqual(task_name, o_name)

            # The launch and start times should be the same (to first decimal)
            self.assertEqual(o_launch, o_start)
            t_delta = (o_launch - expected_time).total_seconds()
            self.assertAlmostEqual(0, t_delta, places=0)

            # End and completed should be none unless it's the first task
            if task_name != modified_task:
                self.assertTrue(o_end is None)
                self.assertTrue((o_completed is None) or (o_completed != 1))
            else:
                # The task should be completed
                self.assertEqual(0, o_completed)

                # Time difference between completion times
                t_delta = (o_end - completion_time).total_seconds()
                self.assertAlmostEqual(0, t_delta, places=0)

        # Closing the connection
        conn.close()

    def test_mark_drmaa_task_completed(self):
        """Tests the 'mark_drmaa_task_completed' function."""
        # The task that will be modified
        modified_task = self.task_names[0]

        # Waiting 1 second and "launch" task
        time.sleep(1)
        launch_time = datetime.now()

        # Waiting 1 second and "start" task
        time.sleep(1)
        start_time = datetime.now()

        # Waiting 3 seconds and "ending" task
        time.sleep(3)
        end_time = datetime.now()
        mark_drmaa_task_completed(modified_task, launch_time.timestamp(),
                                  start_time.timestamp(), end_time.timestamp(),
                                  self.db_name)

        # Creating the connection
        conn, c = _create_db_connection(self.db_name)

        # Checking that the times are the same
        c.execute("SELECT name, launch, start, end, completed FROM gwip_task")
        results = c.fetchall()
        iteration = zip(self.task_names, self.creation_times, results)
        for task_name, expected_time, result in iteration:
            # The observed values
            o_name, o_launch, o_start, o_end, o_completed = result

            # The name should be the same
            self.assertEqual(task_name, o_name)

            # The launch and start times should be the same (to first decimal)
            # for the other tasks
            if o_name != modified_task:
                self.assertEqual(o_launch, o_start)
                t_delta = (o_launch - expected_time).total_seconds()
                self.assertAlmostEqual(0, t_delta, places=0)
            else:
                self.assertAlmostEqual(launch_time.timestamp(),
                                       o_launch.timestamp(), places=0)
                self.assertAlmostEqual(start_time.timestamp(),
                                       o_start.timestamp(), places=0)
                self.assertAlmostEqual(end_time.timestamp(), o_end.timestamp(),
                                       places=0)

            # End and completed should be none unless it's the first task
            if task_name != modified_task:
                self.assertTrue(o_end is None)
                self.assertTrue(o_completed is None)
            else:
                # The task should be completed
                self.assertEqual(1, o_completed)

                # Time difference between completion times
                t_delta = (o_end - end_time).total_seconds()
                self.assertAlmostEqual(0, t_delta, places=0)

                # Time difference between launch and start should be 1
                t_delta = (o_start - o_launch).total_seconds()
                self.assertAlmostEqual(1, t_delta, places=0)

                # Time difference between start and end should be 3
                t_delta = (o_end - o_start).total_seconds()
                self.assertAlmostEqual(3, t_delta, places=0)

        conn.close()

    def test_get_task_runtime(self):
        """Tests the 'task_runtime' function."""
        # Those two tasks will be modified
        modified_task_1 = self.task_names[0]
        modified_task_2 = self.task_names[1]

        # Waiting 1 second and "launch" task
        time.sleep(1)
        launch_time = datetime.now()

        # Waiting 1 second and "start" task
        time.sleep(1)
        start_time = datetime.now()

        # Waiting 3 seconds and "ending" two task
        time.sleep(3)
        end_time = datetime.now()
        mark_task_completed(modified_task_1, self.db_name)
        mark_drmaa_task_completed(modified_task_2, launch_time.timestamp(),
                                  start_time.timestamp(), end_time.timestamp(),
                                  self.db_name)

        # Getting the first task time
        task_time_1 = get_task_runtime(modified_task_1, self.db_name)
        task_time_2 = get_task_runtime(modified_task_2, self.db_name)

        # Comparing the time
        self.assertEqual(5, task_time_1)
        self.assertEqual(3, task_time_2)

    def test_get_all_runtimes(self):
        """Tests the 'get_all_runtimes' function."""
        # Waiting one second for each task
        start = self.creation_times[-1].timestamp()
        for task_name in self.task_names:
            time.sleep(1)
            if task_name != self.task_names[-1]:
                mark_task_completed(task_name, self.db_name)

            else:
                now = datetime.now().timestamp()
                mark_drmaa_task_completed(task_name, start, start, now,
                                          self.db_name)

        # The expected time
        expected_time = {
            task_name: i + 1 for i, task_name in enumerate(self.task_names)
        }

        # Getting the time for all tasks
        observed_time = get_all_runtimes(self.db_name)
        self.assertEqual(expected_time, observed_time)
