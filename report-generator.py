import json
import csv
from web3 import Web3
from datetime import datetime, timedelta

def get_balance(w3, address):
    balance = w3.eth.get_balance(address)
    return Web3.from_wei(balance, 'ether')

def load_abi(filename):
    with open(filename, 'r') as f:
        return json.load(f)

def get_adapter_events(w3, adapter_contract_address, from_block, to_block, abi):
    contract = w3.eth.contract(address=adapter_contract_address, abi=abi)
    events = contract.events.RandomnessRequestResult.get_logs(fromBlock=from_block, toBlock=to_block)
    return events

def get_node_registry_events(w3, node_registry_contract_address, from_block, to_block, abi):
    contract = w3.eth.contract(address=node_registry_contract_address, abi=abi)
    events = contract.events.NodeSlashed.get_logs(fromBlock=from_block, toBlock=to_block)
    return events

def get_block_number_by_timestamp(w3, timestamp, direction='before'):
    left = 1
    right = w3.eth.get_block('latest')['number']
    
    while left <= right:
        mid = (left + right) // 2
        block = w3.eth.get_block(mid)
        if block['timestamp'] == timestamp:
            return mid
        if block['timestamp'] < timestamp:
            left = mid + 1
        else:
            right = mid - 1
    
    if direction == 'before':
        return right
    else:
        return left

def check_balances_and_events(config, adapter_abi, node_registry_abi):
    results = []
    for address in config['node_addresses']:
        insufficient_chains = []
        event_participation = {}
        is_slashed = False
        
        for chain in config['chains']:
            w3 = Web3(Web3.HTTPProvider(chain['rpc_endpoint']))
            
            # Check balance
            balance = get_balance(w3, address)
            if chain['chain_id'] == 1:
                # For chain_id 1, check both balance and events
                if balance < 0.2:
                    insufficient_chains.append(str(chain['chain_id']))
                
                # Get block range for last 31 days
                current_block = w3.eth.get_block('latest')['number']
                current_timestamp = w3.eth.get_block('latest')['timestamp']
                from_timestamp = current_timestamp - (31 * 24 * 60 * 60)  # 31 days ago
                from_block = get_block_number_by_timestamp(w3, from_timestamp, 'before')
                
                # Check adapter events
                adapter_events = get_adapter_events(w3, chain['adapter_contract_address'], from_block, current_block, adapter_abi)
                
                participated = False
                for event in adapter_events:
                    if address in event['args']['participantMembers']:
                        participated = True
                        break
                
                event_participation[chain['chain_id']] = participated
                
                # Check node registry events
                node_registry_events = get_node_registry_events(w3, chain['node_registry_contract_address'], from_block, current_block, node_registry_abi)
                
                for event in node_registry_events:
                    if event['args']['nodeIdAddress'] == address:
                        is_slashed = True
                        break
            else:
                # For other chains, only check if balance is greater than 0.05
                if balance < 0.05:
                    insufficient_chains.append(str(chain['chain_id']))
            
            if is_slashed:
                break  # No need to check other chains if slashed
        
        is_sufficient = len(insufficient_chains) == 0
        is_participating = event_participation.get(1, False)  # Only check participation for chain_id 1
        
        results.append({
            'Address': address,
            'Insufficient Chain Ids': '|'.join(insufficient_chains),
            'Is Sufficient': is_sufficient,
            'Has Participated in Randomness Tasks': is_participating,
            'Has Been Slashed': is_slashed,
            'Overall Status': is_sufficient and is_participating and not is_slashed
        })
    
    return results

def main():
    with open('config.json', 'r') as f:
        config = json.load(f)
    
    adapter_abi = load_abi('adapter_abi.json')
    node_registry_abi = load_abi('node_registry_abi.json')
    
    results = check_balances_and_events(config, adapter_abi, node_registry_abi)
    
    with open('balance_event_and_slash_check_results.csv', 'w', newline='') as csvfile:
        fieldnames = ['Address', 'Insufficient Chain Ids', 'Is Sufficient', 'Has Participated in Randomness Tasks', 'Has Been Slashed', 'Overall Status']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for result in results:
            writer.writerow(result)
    
    print("Results have been written to balance_event_and_slash_check_results.csv")

if __name__ == "__main__":
    main()