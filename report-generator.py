import json
import csv
from web3 import Web3
from datetime import datetime, timedelta
from web3.middleware import geth_poa_middleware

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
    
    return right if direction == 'before' else left

def get_balance(w3, address):
    balance_wei = w3.eth.get_balance(address)
    return w3.from_wei(balance_wei, 'ether')

def fetch_adapter_events(w3, chain, adapter_abi):
    current_block = w3.eth.get_block('latest')['number']
    current_timestamp = w3.eth.get_block('latest')['timestamp']
    from_timestamp = current_timestamp - (30 * 24 * 60 * 60)  # 30 days ago
    from_block = get_block_number_by_timestamp(w3, from_timestamp, 'before')
    
    return get_adapter_events(w3, chain['adapter_contract_address'], from_block, current_block, adapter_abi)

def fetch_node_registry_events(w3, chain, node_registry_abi):
    current_block = w3.eth.get_block('latest')['number']
    current_timestamp = w3.eth.get_block('latest')['timestamp']
    from_timestamp = current_timestamp - (30 * 24 * 60 * 60)  # 30 days ago
    from_block = get_block_number_by_timestamp(w3, from_timestamp, 'before')
    
    return get_node_registry_events(w3, chain['node_registry_contract_address'], from_block, current_block, node_registry_abi)

def process_events(adapter_events, addresses):
    participation = {addr: False for addr in addresses}
    
    for event in adapter_events:
        for participant in event['args']['participantMembers']:
            if participant.lower() in [addr.lower() for addr in addresses]:
                participation[next(addr for addr in addresses if addr.lower() == participant.lower())] = True
    
    return participation

def check_balances_and_events(config, adapter_abi, node_registry_abi):
    results = {addr: {'Address': addr, 'Insufficient Chain Ids': [], 'Is Sufficient': True, 'Has Participated in Randomness Tasks': False, 'Has Been Slashed': False, 'Balances': []} for addr in config['node_addresses']}
    
    for chain in config['chains']:
        w3 = Web3(Web3.HTTPProvider(chain['rpc_endpoint']))
        if chain['chain_id'] != 1:
            w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        
        adapter_events = fetch_adapter_events(w3, chain, adapter_abi)
        participation = process_events(adapter_events, config['node_addresses'])
        
        for address in config['node_addresses']:
            balance = get_balance(w3, address)
            results[address]['Balances'].append(f"{chain['chain_id']}:{balance:.4f}")
            
            if (chain['chain_id'] == 1 and balance < 0.2) or (chain['chain_id'] != 1 and balance < 0.05):
                results[address]['Insufficient Chain Ids'].append(str(chain['chain_id']))
                results[address]['Is Sufficient'] = False
            
            if participation[address]:
                results[address]['Has Participated in Randomness Tasks'] = True
        
        if chain['chain_id'] == 1:
            node_registry_events = fetch_node_registry_events(w3, chain, node_registry_abi)
            for event in node_registry_events:
                slashed_address = event['args']['nodeIdAddress']
                if slashed_address in results:
                    results[slashed_address]['Has Been Slashed'] = True
    
    for address, data in results.items():
        data['Insufficient Chain Ids'] = '|'.join(data['Insufficient Chain Ids'])
        data['Balances'] = '|'.join(data['Balances'])
        data['Overall Status'] = data['Is Sufficient'] and data['Has Participated in Randomness Tasks'] and not data['Has Been Slashed']
    
    return list(results.values())

def main():
    with open('config.json', 'r') as f:
        config = json.load(f)
    
    adapter_abi = load_abi('adapter_abi.json')
    node_registry_abi = load_abi('node_registry_abi.json')
    
    results = check_balances_and_events(config, adapter_abi, node_registry_abi)
    
    with open('balance_event_and_slash_check_results.csv', 'w', newline='') as csvfile:
        fieldnames = ['Address', 'Insufficient Chain Ids', 'Is Sufficient', 'Has Participated in Randomness Tasks', 'Has Been Slashed', 'Overall Status', 'Balances']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for result in results:
            writer.writerow(result)
    
    print("Results have been written to balance_event_and_slash_check_results.csv")

if __name__ == "__main__":
    main()