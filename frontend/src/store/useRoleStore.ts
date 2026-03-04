import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { Role } from './models';

interface RoleStore {
  customRoles: Role[];
  addCustomRole: (role: Role) => void;
  removeCustomRole: (id: string) => void;
  updateCustomRole: (id: string, role: Partial<Role>) => void;
  exportRoles: () => void;
  importRoles: (roles: Role[]) => void;
}

export const useRoleStore = create<RoleStore>()(
  persist(
    (set) => ({
      customRoles: [],
      addCustomRole: (role) =>
        set((state) => ({
          customRoles: [...state.customRoles, role],
        })),
      removeCustomRole: (id) =>
        set((state) => ({
          customRoles: state.customRoles.filter((role) => role.id !== id),
        })),
      updateCustomRole: (id, role) =>
        set((state) => ({
          customRoles: state.customRoles.map((r) =>
            r.id === id ? { ...r, ...role } : r
          ),
        })),
      exportRoles: () => {
        const state = window.localStorage.getItem('otakuneko-roles-storage');
        if (state) {
          const parsedState = JSON.parse(state);
          const roles = parsedState.state.customRoles;
          const dataStr = JSON.stringify(roles, null, 2);
          const dataBlob = new Blob([dataStr], { type: 'application/json' });
          const url = URL.createObjectURL(dataBlob);
          const link = document.createElement('a');
          link.href = url;
          link.download = 'otakuneko-roles.json';
          link.click();
          URL.revokeObjectURL(url);
        }
      },
      importRoles: (roles) => {
        set({ customRoles: roles });
      },
    }),
    {
      name: 'otakuneko-roles-storage',
    }
  )
);
