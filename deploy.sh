#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color
YELLOW='\033[1;33m'

echo -e "${YELLOW}Starting deployment process...${NC}"

# Step 1: SSH to first server
echo -e "\n${YELLOW}Step 1: Connecting to first server...${NC}"
ssh root@103.3.63.207 "
    echo -e '${GREEN}Connected to first server${NC}'
    
    # Step 2: SSH to second server with key forwarding
    echo -e '\n${YELLOW}Step 2: Connecting to second server...${NC}'
    ssh -A -i ./algo/configs/algo.pem root@138.197.130.28 '
        echo -e \"${GREEN}Connected to second server${NC}\"
        
        # Step 3: Change directory
        echo -e \"\n${YELLOW}Step 3: Changing to project directory...${NC}\"
        cd simple-spot-trading-bot
        
        # Step 4: Activate virtual environment
        echo -e \"\n${YELLOW}Step 4: Activating virtual environment...${NC}\"
        source venv/bin/activate
        
        # Step 5: Stop the bot
        echo -e \"\n${YELLOW}Step 5: Stopping the bot...${NC}\"
        ./stop.sh
        sleep 2
        
        # Step 6: Pull latest changes
        echo -e \"\n${YELLOW}Step 6: Pulling latest changes...${NC}\"
        git pull -r
        
        # Step 7: load environment variable
        echo -e \"\n${YELLOW}Step 7: Loading environment variable...${NC}\"
        source ~/.bashrc

        # Step 8: Start the bot
        echo -e \"\n${YELLOW}Step 7: Starting the bot...${NC}\"
        ./start.sh
        sleep 5
        
        # Step 9: Check if bot is running
        echo -e \"\n${YELLOW}Step 8: Checking bot status...${NC}\"
        if pgrep -f \"python.*main.py\" > /dev/null; then
            echo -e \"${GREEN}Bot is running successfully!${NC}\"
            
            # Get PID and basic info
            PID=$(pgrep -f \"python.*main.py\")
            echo -e \"${GREEN}Process ID: ${PID}${NC}\"
            
            # Check log file for recent activity
            echo -e \"\n${YELLOW}Recent log entries:${NC}\"
            tail -n 5 logs/bot/bot.log
        else
            echo -e \"${RED}Error: Bot is not running!${NC}\"
            echo -e \"${YELLOW}Checking error logs:${NC}\"
            tail -n 10 logs/bot/bot.log
            exit 1
        fi
    '
"

# Check the final exit status
if [ $? -eq 0 ]; then
    echo -e "\n${GREEN}Deployment completed successfully!${NC}"
else
    echo -e "\n${RED}Deployment failed!${NC}"
    exit 1
fi
