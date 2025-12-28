import { create } from 'zustand';
import { Subject } from '@/lib/api';

interface ManualAddDialogState {
  isOpen: boolean;
  selectedSubject: Subject | null;
  openDialog: (subject?: Subject) => void;
  closeDialog: () => void;
}

export const useManualAddDialogStore = create<ManualAddDialogState>((set) => ({
  isOpen: false,
  selectedSubject: null,
  openDialog: (subject) => set({ isOpen: true, selectedSubject: subject || null }),
  closeDialog: () => set({ isOpen: false, selectedSubject: null })
}));
