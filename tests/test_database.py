from sem import DatabaseManager
import pytest
import os
from copy import deepcopy


############
# Fixtures #
############

@pytest.fixture(scope='function')
def db(config):
    """
    Provide a valid database, initialized with an example configuration.
    """
    return DatabaseManager.new(**config)

#################################
# Database creation and loading #
#################################


def test_db_creation_from_scratch(tmpdir, config, ns_3):
    # This should be ok
    DatabaseManager.new(**config)
    # This should raise FileExistsError because directory already exists
    with pytest.raises(FileExistsError):
        DatabaseManager.new(**config)
    # This should execute no problem because we overwrite the database
    DatabaseManager.new(**config, overwrite=True)


def test_db_loading(config, db, tmpdir):
    # Note that the db fixture initializes a db for us
    # Load the database file
    db = DatabaseManager.load(config['campaign_dir'])

    # Make sure campaign dir is correct
    assert db.campaign_dir == config['campaign_dir']

    # Check for a correctly loaded configuration
    del config['campaign_dir']
    assert db.get_config() == config


#####################
# Utility functions #
#####################


def test_getters(db, tmpdir, config):
    # Saved configuration should not include the campaign directory
    del config['campaign_dir']
    assert db.get_config() == config
    assert db.get_data_dir() == os.path.join(tmpdir, 'test_campaign', 'data')


def test_get_next_rngruns(db, result):
    # First rngrun of a new campaign should be 0
    assert db.get_next_rngruns() == [0]

    # If we add a result with RngRun 2, this should still return 0
    result['params']['RngRun'] = 2
    db.insert_result(result)
    assert db.get_next_rngruns() == [0]

    # After inserting a run with index 0, we expect a 1
    result['params']['RngRun'] = 0
    db.insert_result(result)
    assert db.get_next_rngruns() == [1]

    # Finally, if we ask for three more available runs, this should return
    # [1, 3, 4]
    assert db.get_next_rngruns(3) == [1, 3, 4]


def test_results(db, result):
    # Test insertion of valid result
    db.insert_result(result)

    # Test insertion of result missing a parameter
    with pytest.raises(ValueError):
        nonvalid_result = deepcopy(result)
        nonvalid_result['params'].pop('dict')
        db.insert_result(nonvalid_result)

    # Test insertion of result missing any other key
    for k in result.keys():
        with pytest.raises(ValueError):
            db.insert_result({i: result[i] for i in result.keys() if i != k})

    # All inserted results are returned by get_results
    assert db.get_results() == [result]

    db.insert_result(result)
    db.insert_result(result)
    db.insert_result(result)

    assert db.get_results() == [result, result, result, result]

    # wipe_results actually empties result list
    db.wipe_results()
    assert db.get_results() == []


def test_results_queries(db, result):
    # Insert multiple runs for a set parameter combination
    first_round_of_results = []
    for runIdx in range(10):
        result['params']['RngRun'] = runIdx
        first_round_of_results.append(result)
        db.insert_result(result)

    # Query should return the previously saved results
    results = db.get_results()
    assert len(results) == 10
    assert sorted([d['params']['RngRun'] for d in results]) == list(range(10))

    # Insert other runs for a different parameter combination
    result['params']['dict'] = '/usr/share/dict/web2a'
    for runIdx in range(10, 20, 1):
        result['params']['RngRun'] = runIdx
        db.insert_result(result)

    # This query should return all results
    results = db.get_results({'dict': ['/usr/share/dict/web2a',
                                       '/usr/share/dict/web2']})
    assert len(results) == 20
    assert sorted([d['params']['RngRun'] for d in results]) == list(range(20))

    # This one should only return the second batch
    results = db.get_results({'dict': ['/usr/share/dict/web2a']})
    assert len(results) == 10
    assert sorted([d['params']['RngRun'] for d in results]) == list(range(10,
                                                                          20,
                                                                          1))


def test_get_result_files(manager, parameter_combination):
    manager.run_simulations([parameter_combination], show_progress=False)
    assert manager.db.get_complete_results()[0].get('output').get('stdout') is not None
