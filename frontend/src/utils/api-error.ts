import axios from 'axios';

export const apiErrorMessage = (err: unknown): string => {
  if (!axios.isAxiosError(err)) return 'Something went wrong';
  if (err.code === 'ECONNABORTED' || /timeout/i.test(err.message)) {
    return 'Decision check timed out; new entries stay blocked until the check completes';
  }
  return String(err.response?.data?.detail ?? err.message);
};
