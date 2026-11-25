import { defineStore } from 'pinia'
import { computed, shallowRef } from 'vue'
import { areFriends, buildCatalog, mockRepository, permissionsFor, projectedMeals } from '../api/mockRepository'
import { mediaRepository } from '../api/mediaRepository'
import { grantKey, seedDiary, users } from '../mocks/seed'
import type { DateKey, DiaryState, Meal, SharePermission } from '../types/domain'

export const useDiary = defineStore('diary', () => {
  const state = shallowRef(mockRepository.load())
  const account = computed(() => users.find(user => user.id === state.value.activeUserId) ?? users[0])

  function update(patch: Partial<DiaryState>) {
    const next = { ...state.value, ...patch }
    mockRepository.save(next)
    state.value = next
  }
  const person = (id: string) => users.find(user => user.id === id)
  const selectAccount = (id: string) => { if (person(id)) update({ activeUserId: id }) }
  const permissions = (owner: string, viewer = account.value.id) => permissionsFor(state.value, owner, viewer)
  const meals = (date?: DateKey, owner = account.value.id) => projectedMeals(state.value, owner, account.value.id, date)
  const catalog = (owner = account.value.id) => buildCatalog(state.value, owner, account.value.id)
  const isFriend = (id: string) => areFriends(state.value, id, account.value.id)
  const relationships = computed(() => state.value.friends.filter(friend =>
    friend.senderId === account.value.id || friend.recipientId === account.value.id))
  const otherId = (relationship: DiaryState['friends'][number]) =>
    relationship.senderId === account.value.id ? relationship.recipientId : relationship.senderId

  function saveMeal(meal: Meal) {
    if (meal.ownerId !== account.value.id) return false
    const previous = state.value.meals.find(item => item.id === meal.id)
    if (previous && previous.ownerId !== account.value.id) return false
    update({ meals: [...state.value.meals.filter(item => item.id !== meal.id), meal] })
    if (previous?.photo && previous.photo.id !== meal.photo?.id) void mediaRepository.delete(previous.photo.id).catch(() => {})
    return true
  }
  function deleteMeal(id: string) {
    const meal = state.value.meals.find(item => item.id === id && item.ownerId === account.value.id)
    if (!meal) return
    update({ meals: state.value.meals.filter(item => item.id !== meal.id) })
    if (meal.photo) void mediaRepository.delete(meal.photo.id).catch(() => {})
  }
  function favorite(id: string) {
    const owner = account.value.id
    const current = state.value.favorites[owner] ?? []
    const next = current.includes(id) ? current.filter(value => value !== id) : [...current, id]
    update({ favorites: { ...state.value.favorites, [owner]: next } })
  }
  function changeGrant(viewer: string, grant: SharePermission) {
    if (!isFriend(viewer)) return
    update({ grants: { ...state.value.grants, [grantKey(account.value.id, viewer)]: { ...grant } } })
  }
  function requestFriend(id: string) {
    const senderId = account.value.id
    if (!person(id) || id === senderId || relationships.value.some(friend => otherId(friend) === id && friend.status !== 'rejected')) return false
    const remaining = state.value.friends.filter(friend => otherId(friend) !== id || !relationships.value.includes(friend))
    update({ friends: [...remaining, { id: crypto.randomUUID(), senderId, recipientId: id, status: 'pending' }] })
    return true
  }
  function answerRequest(id: string, status: 'accepted' | 'rejected') {
    update({ friends: state.value.friends.map(friend => friend.id === id && friend.recipientId === account.value.id && friend.status === 'pending'
      ? { ...friend, status } : friend) })
  }
  async function reset() {
    await mediaRepository.clear()
    update(seedDiary())
  }
  return { account, person, selectAccount, meals, catalog, permissions, isFriend, relationships, otherId,
    saveMeal, deleteMeal, favorite, changeGrant, requestFriend, answerRequest, reset }
})
