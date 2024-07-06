def get_daily_reward_task(daily_tasks):
    for i in range(len(daily_tasks)):
        if daily_tasks[i].get("code") == "dailyReward":
            daily_tasks_max_amount = daily_tasks[i].get("maxAmount")
            daily_tasks_done_amount = daily_tasks[i].get("doneAmount")
            daily_tasks_current_day = daily_tasks[i].get("currentDay")
        return daily_tasks_max_amount, daily_tasks_done_amount, daily_tasks_current_day
    return None
