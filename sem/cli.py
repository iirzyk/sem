import click
import sem
import ast


@click.group()
def cli():
    """
    An interface to the ns-3 Simulation Execution Manager.
    """
    pass

@cli.command()
@click.option("--ns-3-path", type=click.Path(exists=True,
                                             resolve_path=True),
              prompt=True)
@click.option("--results-dir", type=click.Path(dir_okay=True,
                                               resolve_path=True),
              prompt=True)
@click.option("--script", prompt=True)
@click.option("--no-optimization", default=False, is_flag=True)
def run(ns_3_path, results_dir, script, no_optimization):
    """
    Run simulations from the command line.
    """
    if sem.utils.DRMAA_AVAILABLE:
        click.echo("Detected available DRMAA cluster: Using GridRunner.")
        runner_type = "GridRunner"
    else:
        runner_type = "ParallelRunner"

    # Create a campaign
    campaign = sem.CampaignManager.new(ns_3_path,
                                       script,
                                       results_dir,
                                       runner_type=runner_type,
                                       overwrite=False,
                                       optimized=not no_optimization)

    # Print campaign info
    click.echo(campaign)

    # Query parameters
    script_params = {k: [] for k in campaign.db.get_params()}
    for param in script_params.keys():
        script_params[param] = ast.literal_eval(click.prompt("%s" % param))

    # Run the simulations
    campaign.run_missing_simulations(script_params,
                                     runs=click.prompt("Runs", type=int))