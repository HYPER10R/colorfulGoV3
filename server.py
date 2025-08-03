# server.py
import asyncio
import websockets
import json
import random
import string
from datetime import datetime

# 游戏配置
CONFIG = {
    'BOARD_SIZE': 19,
    'MAX_PLAYERS': 7,
    'ROOM_CODE_LENGTH': 6,
    'PLAYER_COLORS': [
        '#FF0000',  # 红
        '#FF7700',  # 橙
        '#FFFF00',  # 黄
        '#00FF00',  # 绿
        '#00FFFF',  # 青
        '#0000FF',  # 蓝
        '#8A2BE2'   # 紫
    ],
    'PLAYER_NAMES': ['红色', '橙色', '黄色', '绿色', '青色', '蓝色', '紫色']
}

# 存储游戏房间
game_rooms = {}

class GameRoom:
    def __init__(self, room_code):
        self.room_code = room_code
        self.players = {}  # websocket -> player_info
        self.board = [[None for _ in range(CONFIG['BOARD_SIZE'])] for _ in range(CONFIG['BOARD_SIZE'])]
        self.current_player = 0
        self.move_count = 0
        self.pass_count = 0
        self.scores = [0.0] * CONFIG['MAX_PLAYERS']
        self.captured_stones = []
        self.game_over = False
        self.created_at = datetime.now()

    def add_player(self, websocket):
        if len(self.players) >= CONFIG['MAX_PLAYERS']:
            return False
        
        player_id = len(self.players)
        self.players[websocket] = {
            'id': player_id,
            'name': CONFIG['PLAYER_NAMES'][player_id],
            'color': CONFIG['PLAYER_COLORS'][player_id],
            'ready': False
        }
        return True

    def remove_player(self, websocket):
        if websocket in self.players:
            del self.players[websocket]

    def get_player_count(self):
        return len(self.players)

    def all_players_ready(self):
        return all(player['ready'] for player in self.players.values()) and len(self.players) == CONFIG['MAX_PLAYERS']

    def set_player_ready(self, websocket):
        if websocket in self.players:
            self.players[websocket]['ready'] = True

    def get_game_state(self):
        return {
            'board': self.board,
            'currentPlayer': self.current_player,
            'moveCount': self.move_count,
            'scores': self.scores,
            'players': list(self.players.values()),
            'gameOver': self.game_over
        }

    def place_stone(self, x, y, player_id):
        if self.game_over or self.board[x][y] is not None:
            return False

        self.board[x][y] = player_id
        self.move_count += 1
        self.pass_count = 0

        # 检查吃子
        self.check_captures(x, y)

        # 切换玩家
        self.current_player = (self.current_player + 1) % len(self.players)

        return True

    def pass_turn(self, player_id):
        if self.game_over:
            return

        self.pass_count += 1
        self.move_count += 1

        # 切换玩家
        self.current_player = (self.current_player + 1) % len(self.players)

        if self.pass_count >= 2:
            self.game_over = True
            self.calculate_area_control_scores()

    def check_captures(self, x, y):
        # 检查周围四个方向的棋子
        directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        surrounding_players = set()

        for dx, dy in directions:
            nx, ny = x + dx, y + dy
            if 0 <= nx < CONFIG['BOARD_SIZE'] and 0 <= ny < CONFIG['BOARD_SIZE']:
                player = self.board[nx][ny]
                if player is not None:
                    surrounding_players.add(player)

        # 如果被四个不同玩家包围
        if len(surrounding_players) == 4:
            captured_player = self.board[x][y]
            self.board[x][y] = None

            # 四个包围者各得0.25分
            for player_id in surrounding_players:
                self.scores[player_id] += 0.25

            self.captured_stones.append({
                'x': x, 'y': y, 'player': captured_player,
                'captors': list(surrounding_players)
            })


    def calculate_area_control_scores(self):
        """按每个玩家所占棋子格子数进行评分"""
        area_scores = [0] * CONFIG['MAX_PLAYERS']
        for row in self.board:
            for cell in row:
                if cell is not None:
                    area_scores[cell] += 1
        self.scores = area_scores

    def reset_game(self):
        self.board = [[None for _ in range(CONFIG['BOARD_SIZE'])] for _ in range(CONFIG['BOARD_SIZE'])]
        self.current_player = 0
        self.move_count = 0
        self.pass_count = 0
        self.scores = [0.0] * CONFIG['MAX_PLAYERS']
        self.captured_stones = []
        self.game_over = False

def generate_room_code():
    """生成唯一的6位房间代码"""
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=CONFIG['ROOM_CODE_LENGTH']))
        if code not in game_rooms:
            return code

async def register(websocket):
    """处理新的WebSocket连接"""
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                print(f"收到消息: {data}")  # 调试信息
                
                action = data.get('action')
                if not action:
                    continue

                if action == 'create_room':
                    # 创建新房间
                    room_code = generate_room_code()
                    game_rooms[room_code] = GameRoom(room_code)
                    game_rooms[room_code].add_player(websocket)
                    
                    response = {
                        'action': 'room_created',
                        'room_code': room_code,
                        'player_id': 0,
                        'message': f'房间创建成功，房间代码: {room_code}'
                    }
                    await websocket.send(json.dumps(response))
                    print(f"创建房间: {room_code}")

                elif action == 'join_room':
                    # 加入现有房间
                    room_code = data.get('room_code', '')
                    print(f"尝试加入房间: '{room_code}'")
                    
                    # 确保房间代码是字符串并转为大写
                    if room_code is not None:
                        room_code = str(room_code).strip().upper()
                    
                    print(f"处理后的房间代码: '{room_code}'")
                    print(f"现有房间: {list(game_rooms.keys())}")
                    
                    if room_code and room_code in game_rooms:
                        room = game_rooms[room_code]
                        if room.add_player(websocket):
                            player_id = len(room.players) - 1
                            response = {
                                'action': 'joined_room',
                                'room_code': room_code,
                                'player_id': player_id,
                                'message': f'成功加入房间 {room_code}'
                            }
                            await websocket.send(json.dumps(response))
                            
                            # 通知所有玩家更新房间信息
                            await broadcast_room_update(room)
                        else:
                            response = {
                                'action': 'error',
                                'message': '房间已满'
                            }
                            await websocket.send(json.dumps(response))
                    else:
                        response = {
                            'action': 'error',
                            'message': f'房间不存在: {room_code}'
                        }
                        await websocket.send(json.dumps(response))

                elif action == 'player_ready':
                    # 玩家准备
                    room_code = data.get('room_code', '')
                    if room_code is not None:
                        room_code = str(room_code).strip().upper()
                    
                    if room_code and room_code in game_rooms:
                        room = game_rooms[room_code]
                        room.set_player_ready(websocket)
                        
                        # 检查是否所有玩家都准备好了
                        if room.all_players_ready():
                            response = {
                                'action': 'game_start',
                                'game_state': room.get_game_state()
                            }
                            await broadcast_to_room(room, response)
                        else:
                            await broadcast_room_update(room)

                elif action == 'place_stone':
                    # 放置棋子
                    room_code = data.get('room_code', '')
                    x = data.get('x')
                    y = data.get('y')
                    player_id = data.get('player_id')
                    
                    if room_code is not None:
                        room_code = str(room_code).strip().upper()
                    
                    if room_code and room_code in game_rooms and x is not None and y is not None and player_id is not None:
                        room = game_rooms[room_code]
                        if room.current_player == player_id:
                            if room.place_stone(x, y, player_id):
                                # 广播游戏状态更新
                                response = {
                                    'action': 'game_update',
                                    'game_state': room.get_game_state(),
                                    'move_info': {
                                        'type': 'place',
                                        'x': x,
                                        'y': y,
                                        'player_id': player_id
                                    }
                                }
                                await broadcast_to_room(room, response)

                elif action == 'pass_turn':
                    # 跳过回合
                    room_code = data.get('room_code', '')
                    player_id = data.get('player_id')
                    
                    if room_code is not None:
                        room_code = str(room_code).strip().upper()
                    
                    if room_code and room_code in game_rooms and player_id is not None:
                        room = game_rooms[room_code]
                        if room.current_player == player_id:
                            room.pass_turn(player_id)
                            
                            response = {
                                'action': 'game_update',
                                'game_state': room.get_game_state(),
                                'move_info': {
                                    'type': 'pass',
                                    'player_id': player_id
                                }
                            }
                            await broadcast_to_room(room, response)

                elif action == 'reset_game':
                    # 重新开始游戏
                    room_code = data.get('room_code', '')
                    if room_code is not None:
                        room_code = str(room_code).strip().upper()
                    
                    if room_code and room_code in game_rooms:
                        room = game_rooms[room_code]
                        room.reset_game()
                        
                        response = {
                            'action': 'game_reset',
                            'game_state': room.get_game_state()
                        }
                        await broadcast_to_room(room, response)

            except json.JSONDecodeError:
                print(f"JSON解析错误: {message}")
                continue
            except Exception as e:
                print(f"处理消息时出错: {e}")
                import traceback
                traceback.print_exc()
                continue

    except websockets.exceptions.ConnectionClosed:
        print("客户端连接关闭")
    except Exception as e:
        print(f"连接处理出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 清理连接
        rooms_to_remove = []
        for room_code, room in list(game_rooms.items()):
            room.remove_player(websocket)
            if room.get_player_count() == 0:
                rooms_to_remove.append(room_code)
            else:
                await broadcast_room_update(room)
        
        # 删除空房间
        for room_code in rooms_to_remove:
            if room_code in game_rooms:
                del game_rooms[room_code]
                print(f"删除空房间: {room_code}")

async def broadcast_to_room(room, message):
    """向房间内所有玩家广播消息"""
    if isinstance(message, dict):
        message = json.dumps(message)
    
    disconnected = set()
    for websocket in list(room.players.keys()):  # 使用list避免在迭代时修改字典
        try:
            await websocket.send(message)
        except websockets.exceptions.ConnectionClosed:
            disconnected.add(websocket)
        except Exception as e:
            print(f"广播消息时出错: {e}")
            disconnected.add(websocket)
    
    # 移除断开连接的玩家
    for websocket in disconnected:
        room.remove_player(websocket)

async def broadcast_room_update(room):
    """广播房间更新信息"""
    response = {
        'action': 'room_update',
        'player_count': room.get_player_count(),
        'players': list(room.players.values()),
        'all_ready': room.all_players_ready()
    }
    await broadcast_to_room(room, response)

async def main():
    """主函数"""
    # 启动服务器
    print("正在启动围棋联机服务器...")
    print("现有房间:", list(game_rooms.keys()))
    async with websockets.serve(register, "localhost", 8765):
        print("围棋联机服务器启动在 ws://localhost:8765")
        print("等待玩家连接...")
        await asyncio.Future()  # 运行直到被中断

# 启动服务器
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n服务器已关闭")
    except Exception as e:
        print(f"服务器启动失败: {e}")
        import traceback
        traceback.print_exc()
