import client from './client'

export type AuthUserDto = { id: number; username: string }

export const fetchAuthUsers = () =>
  client.get<AuthUserDto[]>('/auth/users').then((r) => r.data)

export const fetchSession = () =>
  client.get<AuthUserDto>('/auth/session').then((r) => r.data)
