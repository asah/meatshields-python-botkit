# Skeleton API server for writing meatshields bots
see https://meatshields.com/createBotGuide.php for official documentation.

# Trying the nullbot
To play the nullbot, visit https://meatshields.com/playUserBot.php and select "null bot"

To register the nullbot for yourself, visit https://meatshields.com/addUpdateBot.php and add this URL: http://meatshields-nullbot.jewsforbacon.com:5000

# Installing Flask-Restful on Ubuntu 16.04
protip: remember to open port 5000 so the meatshields can talk to your bot.

protip: for production use, remember to add your bot to the OS startup scripts, e.g. https://linuxconfig.org/how-to-automatically-execute-shell-script-at-startup-boot-on-systemd-linux

```
pip3 install flask flask-restful
```

# Running the bot server
```shell
./run.sh
 * Serving Flask app "nullbot"
 * Forcing debug mode on
 * Running on http://0.0.0.0:5000/ (Press CTRL+C to quit)
 * Restarting with stat
 * Debugger is active!
 * Debugger PIN: 215-502-141
```

# Testing the heartbeat interface
```shell
./test_heartbeat.sh
OK
```

# Testing the nextmove interface
```shell
./test_nextmove.sh
{
    "status": "success",
    "data": {
        "purchase": false,
        "end_turn": true,
        "move": false
    }
}
```

# Running the server simulator
This causes basicbot.py to play against itself. 

```shell
./sim.py
```

# Docker

```
docker build . -t meatshields-python-botkit:1.0
docker run -it -d --name ms-01 meatshields-python-botkit:1.0
docker exec -it ms-01 bash -c "cd ms; pypy sim.py"
docker kill ms-01; docker rm ms-01
```

or get fancy:
```
docker exec -it ms-01 bash -c "cd ms; DBG_PARALLEL_MOVE_DISCOVERY=1 PARALLEL_MOVE_DISCOVERY=1 BOARD_FILENAME=test_attacking.json pypy sim.py"
```

rapid development:
```
tar czf - *.py *.json | docker exec -i ms-01 bash -c "cd ms; tar xzvf -"
# ... then run the docker commands above to rebuild, re-run and restart
```


