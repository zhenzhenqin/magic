import { permissionKeys } from '../types/domain'
import type { DiaryState, FoodCategory, Meal, MealItem, MealKind, SharePermission, User } from '../types/domain'
import { shiftDay, todayKey } from '../utils/dates'

export const users: User[] = [
  { id: 'lin', nickname: '小林', initials: '林', tone: 'sage' },
  { id: 'lan', nickname: '阿岚', initials: '岚', tone: 'peach' },
  { id: 'man', nickname: '小满', initials: '满', tone: 'butter' },
  { id: 'orange', nickname: '橙子', initials: '橙', tone: 'peach' },
  { id: 'yu', nickname: '小鱼', initials: '鱼', tone: 'sage' },
]

export const categories: FoodCategory[] = ['主食', '家常菜', '烘焙甜点', '饮品', '水果', '其他']

interface SeedFood {
  id: string
  name: string
  category: FoodCategory
  weight: number
  calories: number
  macros: [number, number, number]
}

export const foods: SeedFood[] = [
  { id: 'croissant', name: '黄油可颂', category: '烘焙甜点', weight: 65, calories: 245, macros: [5, 29, 12] },
  { id: 'milk', name: '鲜牛奶', category: '饮品', weight: 180, calories: 109, macros: [6, 9, 6] },
  { id: 'curry', name: '日式咖喱饭', category: '主食', weight: 325, calories: 480, macros: [17, 64, 17] },
  { id: 'ramen', name: '豚骨拉面', category: '主食', weight: 400, calories: 510, macros: [23, 59, 19] },
  { id: 'sushi', name: '三文鱼寿司', category: '主食', weight: 135, calories: 196, macros: [11, 27, 5] },
  { id: 'fried-rice', name: '鸡蛋炒饭', category: '主食', weight: 250, calories: 398, macros: [14, 61, 11] },
  { id: 'tomato-eggs', name: '番茄炒蛋', category: '家常菜', weight: 220, calories: 224, macros: [12, 13, 14] },
  { id: 'cake', name: '草莓奶油蛋糕', category: '烘焙甜点', weight: 110, calories: 285, macros: [5, 34, 14] },
  { id: 'coffee', name: '燕麦拿铁', category: '饮品', weight: 230, calories: 135, macros: [3, 19, 5] },
  { id: 'strawberries', name: '新鲜草莓', category: '水果', weight: 100, calories: 32, macros: [1, 8, 0] },
  { id: 'burger', name: '芝士牛肉汉堡', category: '主食', weight: 245, calories: 590, macros: [28, 52, 30] },
  { id: 'pasta', name: '番茄意大利面', category: '主食', weight: 280, calories: 410, macros: [14, 65, 11] },
]

export const foodSeed = (id: string) => foods.find(food => food.id === id)

export function sampleItem(foodId: string, id: string = crypto.randomUUID()): MealItem {
  const food = foodSeed(foodId)!
  const [protein, carbs, fat] = food.macros
  return { id, foodId, name: food.name, category: food.category, stickerId: foodId,
    weight: food.weight, calories: food.calories, nutrition: { protein, carbs, fat } }
}

export function newPermissions(value = false): SharePermission {
  return Object.fromEntries(permissionKeys.map(key => [key, value])) as SharePermission
}

export function grantKey(ownerId: string, viewerId: string) {
  return [ownerId, viewerId].join(':')
}

export function seedDiary(): DiaryState {
  const today = todayKey()
  const meals: Meal[] = []
  function add(ownerId: string, offset: number, kind: MealKind, time: string, ids: string[], note = '') {
    const date = shiftDay(today, offset)
    const id = [ownerId, date, kind].join('-')
    meals.push({ id, ownerId, date, kind, time, note, updatedAt: date + 'T' + time + ':00',
      items: ids.map((foodId, index) => sampleItem(foodId, id + '-' + index)) })
  }

  add('lin', 0, 'breakfast', '08:30', ['croissant', 'coffee'], '楼下烘焙店的可颂，今天也刚好出炉。')
  add('lin', 0, 'lunch', '12:40', ['curry'], '午休绕了点路，为了这一盘咖喱。')
  add('lin', 0, 'dinner', '19:10', ['ramen', 'sushi'], '下班后的热汤，喝完觉得很踏实。')
  add('lin', 0, 'snack', '16:20', ['strawberries'], '洗了一小碗，甜得刚刚好。')
  add('lin', -1, 'breakfast', '07:55', ['milk', 'croissant'])
  add('lin', -1, 'lunch', '12:20', ['tomato-eggs'], '熟悉的家常味。')
  add('lin', -2, 'dinner', '18:40', ['pasta'], '周末慢慢煮的番茄酱。')
  add('lin', -3, 'snack', '15:45', ['cake', 'coffee'])
  add('lin', -5, 'lunch', '12:35', ['fried-rice', 'milk'])
  add('lin', -7, 'dinner', '19:25', ['burger'])
  add('lin', -9, 'lunch', '12:30', ['sushi'])
  add('lin', -11, 'breakfast', '09:00', ['coffee'])
  for (const offset of [-14, -16, -19, -23]) add('lin', offset, 'lunch', '12:35', ['curry'])

  add('lan', 0, 'breakfast', '08:05', ['milk', 'cake'], '昨晚留下的一小块蛋糕。')
  add('lan', 0, 'lunch', '12:15', ['fried-rice'], '冰箱里剩的蔬菜都用上了。')
  add('lan', 0, 'dinner', '18:50', ['pasta'], '今天的番茄特别香。')
  add('lan', -1, 'lunch', '12:50', ['ramen'])
  add('man', 0, 'lunch', '13:10', ['burger'], '散步之后的午餐。')
  add('orange', 0, 'snack', '15:30', ['strawberries'])

  return {
    activeUserId: 'lin',
    meals,
    friends: [
      { id: 'lin-lan', senderId: 'lin', recipientId: 'lan', status: 'accepted' },
      { id: 'lin-man', senderId: 'man', recipientId: 'lin', status: 'accepted' },
      { id: 'orange-lin', senderId: 'orange', recipientId: 'lin', status: 'pending' },
    ],
    grants: {
      'lan:lin': { ...newPermissions(true), calories: false, nutrition: false },
      'lin:lan': { ...newPermissions(true), calories: false, nutrition: false, photos: false },
      'lin:man': { ...newPermissions(), records: true, names: true, stickers: true },
    },
    favorites: { lin: ['curry', 'coffee', 'cake'], lan: ['pasta'] },
  }
}
