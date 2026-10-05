export type Role = {
  id: string;
  name: string;
};

export type CreateUserRequest = {
  email: string;
  username: string;
  password: string;
  firstName: string;
  lastName: string;
  phone?: string;
  roleIds: string[];
};