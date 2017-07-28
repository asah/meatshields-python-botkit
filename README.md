# Skeleton API server for writing meatshields bots:

see https://meatshields.com/createBotGuide.php for official documentation.

# installing Flask-Restful on Ubuntu 16.04
pip3 install flask flask-restful

# running the bot server
./run.sh

# testing the heartbeat interface
./test_heartbeat.sh
OK

# test the nextmove interface
./test_nextmove.sh
{
    "status": "success",
    "data": {
        "purchase": false,
        "end_turn": true,
        "move": false
    }
}
