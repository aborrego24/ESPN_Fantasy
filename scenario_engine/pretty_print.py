import sys
import json


def get_clinch_scenarios(team, scenarios):
    for team_entry in scenarios:
        if team in team_entry:
            team_data = team_entry[team].get("clinch_scenarios")
            if team_data:
                win_clinch_scen = team_data[0]
                loss_clinch_scen = team_data[1]
                return win_clinch_scen, loss_clinch_scen
            
def get_elim_scenarios(team, scenarios):
    for team_entry in scenarios:
        if team in team_entry:
            team_data = team_entry[team].get("elim_scenarios")
            if team_data:
                win_elim_scen = team_data[0]
                loss_elim_scen = team_data[1]
                return win_elim_scen, loss_elim_scen

def clean_scenarios(scenarios):
    for team_entry in scenarios:
        for team, data in team_entry.items():
            # Clean clinch_scenarios
            if "clinch_scenarios" in data:
                cleaned_clinch = [
                    [team for team in path if team is not None]
                    for path in data["clinch_scenarios"]
                ]
                data["clinch_scenarios"] = cleaned_clinch
            # Clean elim_scenarios
            if "elim_scenarios" in data:
                cleaned_elim = [
                    [team for team in path if team is not None]
                    for path in data["elim_scenarios"]
                ]
                data["elim_scenarios"] = cleaned_elim
    return scenarios

def main():
    data = json.load(sys.stdin)
    standings = data["base_league_data"]["standings"]
    scenarios = data["scenarios"]
    scenarios = clean_scenarios(scenarios)

    print("\n===================== \033[92mCLINCH SCENARIOS\033[0m =====================")
    for team in standings:
        name = team["team_name"]
        status = team["status"]

        # Already clinched
        if "Clinched" in status:
            print(f"====== \033[92m{name}\033[0m Clinched Playoff Spot ======")
            continue

        clinch_scenario = get_clinch_scenarios(name, scenarios)
        if not clinch_scenario:
            continue  # No clinch scenario section for this team
        win_path, loss_path = clinch_scenario
        print(f"====== \033[92m{name}\033[0m Clinches a playoff spot with: ======")

        # win conditions
        filtered_win = [t for t in win_path if t]
        if filtered_win:
            win_conditions = " and ".join(f"{team} WIN" for team in filtered_win)
            print(f"  - a WIN and {win_conditions}")
        else:
            print(f"  - a WIN")

        if loss_path:
            print("    or ... ")
            filtered_loss = [t for t in loss_path if t]
            if filtered_loss:
                loss_conditions = " and ".join(f"{team} WIN" for team in filtered_loss)
                print(f"  - a LOSS and {loss_conditions}")

    print("\n===================== \033[91mELIMINATION SCENARIOS\033[0m =====================")
    for team in standings:
        name = team["team_name"]
        status = team["status"]

        # Already clinched
        if "Eliminated" in status:
            print(f"====== \033[91m{name}\033[0m Eliminated from playoffs ======")
            continue

        elim_scenario = get_elim_scenarios(name, scenarios)
        if not elim_scenario:
            continue  # No clinch scenario section for this team
        win_path, loss_path = elim_scenario
        print(f"====== \033[91m{name}\033[0m Eliminated from playoffs with: ======")

        # win elim conditions
        filtered_loss = [t for t in loss_path if t]
        if filtered_loss:
            loss_conditions = " and ".join(f"{team} WIN" for team in filtered_loss)
            print(f"  - a LOSS and {win_conditions}")
        else:
            print(f"  - a LOSS")

        if win_path:
            print("    or ... ")
            filtered_win = [t for t in win_path if t]
            if filtered_win:
                win_conditions = " and ".join(f"{team} WIN" for team in filtered_win)
                print(f"  - a LOSS and {win_conditions}")




if __name__ == "__main__": 
    main()
